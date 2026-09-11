const assert = require('node:assert/strict')
const { test } = require('node:test')
const path = require('node:path')
const { buildSync } = require('node:module').createRequire(require.resolve('vite/package.json'))('esbuild')
const React = require('react')
const { renderToStaticMarkup } = require('react-dom/server')

const compiled = new Map()
function load(file, globals = {}) {
  if (!compiled.has(file)) compiled.set(file, buildSync({
    entryPoints: [path.join(__dirname, '../src', file)], bundle: true,
    platform: 'node', format: 'cjs', external: ['react', 'react-dom'], write: false,
  }).outputFiles[0].text)
  const module = { exports: {} }
  new Function('require', 'module', 'exports', ...Object.keys(globals), compiled.get(file))(
    require, module, module.exports, ...Object.values(globals),
  )
  return module.exports
}

const result = {
  run_id: 'offline', status: 'completed', environment: 'test', providers: {},
  request: { question: 'Test study', ticker: 'AAPL', lang: 'zh', template: 'agent_analysis' },
  report: '# Offline report\nReport retained.', planned_stages: ['review'], trace: [],
  evidence: [{ source: 'financials:AAPL', summary: JSON.stringify([
    { ticker: 'AAPL', fiscal_year: 2025, total_revenue: 123456789.12 },
    { ticker: 'AAPL', fiscal_year: 2024, total_revenue: 111222333.45 },
  ]) }],
}
const input = { question: 'q', ticker: null, lang: 'zh' }
test('historical failed reports distinguish unavailable review, rejection and missing evidence', () => {
  const { researchIssue, reportMarkdown } = load('lib/research.ts')
  for (const [detail, expected] of [
    ['Review needs revision: Review could not be completed; report remains unverified.', '自动复核未完成'],
    ['Review did not pass; report requires verification', '未通过自动复核'],
    ['Report generation failed: no evidence available', '未取得可用资料'],
  ]) {
    const failed = { ...result, status: 'failed', trace: [{ stage: 'review', detail }] }
    assert.ok(researchIssue(failed, 'zh').includes(expected))
    assert.ok(reportMarkdown(failed, 'zh').includes('请勿直接采用'))
    assert.equal(failed.status, 'failed')
  }
  assert.equal(researchIssue(result, 'zh'), null)
})
const event = (name, data) => `event: ${name}\r\ndata: ${JSON.stringify(data)}\r\n\r\n`
function stream(text, chunkSize = 7) {
  const bytes = new TextEncoder().encode(text)
  let offset = 0
  return new Response(new ReadableStream({ pull(controller) {
    if (offset === bytes.length) return controller.close()
    controller.enqueue(bytes.slice(offset, offset + chunkSize))
    offset = Math.min(bytes.length, offset + chunkSize)
  } }), { headers: { 'Content-Type': 'text/event-stream' } })
}

test('split SSE frames preserve Chinese text and progress without extra requests', async () => {
  let calls = 0
  const progress = { stage: 'plan', status: 'running' }
  const expected = { ...result, report: '中文研究报告' }
  const api = load('api/research.ts', { fetch: async () => {
    calls++
    return stream(': heartbeat\r\n\r\n' + event('progress', progress) + event('result', expected), 1)
  } })
  const updates = []
  assert.deepEqual(await api.postResearchRun(input, (x) => updates.push(x)), expected)
  assert.deepEqual(updates, [progress])
  assert.equal(calls, 1)
})

for (const status of [404, 405]) {
  test(`only unsupported stream endpoint ${status} falls back once`, async () => {
    const calls = []
    const api = load('api/research.ts', { fetch: async (url, options) => {
      calls.push([url, options.body])
      return calls.length === 1 ? new Response('', { status }) : Response.json(result)
    } })
    assert.deepEqual(await api.postResearchRun(input), result)
    assert.deepEqual(calls.map((x) => x[0]), ['/v1/research/stream', '/v1/research/runs'])
    assert.equal(calls[0][1], calls[1][1])
  })
}

for (const response of [
  () => new Response('', { status: 500 }),
  () => stream(event('progress', { stage: 'plan', status: 'running' })),
  () => stream(event('error', { message: 'Offline failure' })),
]) {
  test('failure or incomplete stream never repeats paid research', async () => {
    let calls = 0
    const api = load('api/research.ts', { fetch: async () => { calls++; return response() } })
    await assert.rejects(api.postResearchRun(input))
    assert.equal(calls, 1)
  })
}

test('context is bounded, successful only and isolated to the selected session', () => {
  const { recentResearch } = load('lib/research.ts')
  const messages = Array.from({ length: 5 }, (_, i) => ({
    role: 'assistant', sessionId: 'one', result: {
      ...result, request: { ...result.request, question: `${i}` }, report: 'a'.repeat(5000),
    },
  }))
  messages.push({ role: 'assistant', sessionId: 'other', result })
  messages.push({ role: 'assistant', sessionId: 'one', result: { ...result, status: 'failed' } })
  const history = recentResearch(messages, 'one')
  assert.deepEqual(history.map((x) => x.question), ['2', '3', '4'])
  assert.ok(history.every((x) => x.answer.length === 4000))
  assert.deepEqual(recentResearch(messages, null), [])
})

test('legacy backend cannot silently discard follow-up context', async () => {
  let calls = 0
  const api = load('api/research.ts', { fetch: async () => { calls++; return new Response('', { status: 404 }) } })
  await assert.rejects(api.postResearchRun({ ...input, history: [{ question: 'q', answer: 'a', ticker: null }] }), /后端/)
  assert.equal(calls, 1)
})

test('personal model requests carry only the login token and never fall back to a system key', async () => {
  const calls = []
  const api = load('api/research.ts', { fetch: async (url, options) => {
    calls.push({ url, options })
    return new Response('', { status: 404 })
  } })
  await assert.rejects(api.postResearchRun(input, undefined, { token: 'offline-login-token' }), /个人 API/)
  assert.equal(calls.length, 1)
  assert.equal(calls[0].url, '/v1/research/personal/stream')
  assert.equal(calls[0].options.headers.Authorization, 'Bearer offline-login-token')
  assert.equal(JSON.parse(calls[0].options.body).api_key, undefined)
  assert.equal(JSON.parse(calls[0].options.body).token, undefined)
})

for (const status of [403, 404, 429, 502]) {
  test(`Codex ${status} fails once without switching API or repeating research`, async () => {
    const calls = []
    const api = load('api/research.ts', { fetch: async (url, options) => {
      calls.push({ url, options })
      return new Response('', { status })
    } })
    await assert.rejects(api.postResearchRun(input, undefined, { token: 'offline-owner', source: 'codex' }))
    assert.equal(calls.length, 1)
    assert.equal(calls[0].url, '/v1/research/codex/stream')
    assert.equal(calls[0].options.headers.Authorization, 'Bearer offline-owner')
    assert.deepEqual(JSON.parse(calls[0].options.body), { ...input, template: 'agent_analysis' })
  })
}

test('export keeps failure warning, source records and numeric precision', () => {
  const { reportMarkdown, safeSourceUrl } = load('lib/research.ts')
  const text = reportMarkdown({ ...result, status: 'failed' }, 'zh')
  assert.match(text, /未完成或未通过审查/)
  assert.match(text, /Report retained/)
  assert.match(text, /123456789.12/)
  assert.equal(safeSourceUrl('javascript:alert(1)'), null)
  assert.equal(safeSourceUrl('https://user:password@example.com'), null)
  assert.equal(safeSourceUrl('https://example.com/report'), 'https://example.com/report')
})

test('failed result retains report and data, offers retry, and never links unsafe URLs', () => {
  const MessageBubble = load('components/MessageBubble.tsx', {
    localStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
  }).default
  const html = renderToStaticMarkup(React.createElement(MessageBubble, {
    message: { id: 'm', sessionId: 's', role: 'assistant', status: 'completed',
      content: 'q', result: { ...result, status: 'failed', evidence: [...result.evidence,
        { source: 'unsafe', summary: '[link](javascript:alert(1))' }],
      } }, lang: 'zh', onRetry: () => {}, retryDisabled: true,
  }))
  assert.match(html, /Report retained/)
  assert.match(html, /重试/)
  assert.match(html, /123456789.12/)
  assert.match(html, /未成功完成或未通过审查/)
  assert.doesNotMatch(html, /href="javascript:/)
  assert.match(html, /class="retry-btn" disabled=""/)
})

test('illustrated report retains missing and negative observations and labels data-only output', () => {
  const ReportFigures = load('components/ReportFigures.tsx').default
  const html = renderToStaticMarkup(React.createElement(ReportFigures, { en: false, data: {
    captured_at: '2025-01-01T00:00:00Z', narrative: 'data_only', metrics: [], summary: [], gaps: ['无估值数据'],
    charts: [{ title: '年度净利润', kind: 'bar', unit: 'USD', labels: ['2023', '2024', '2025'],
      series: [{ name: '净利润', values: [-50, null, 10] }], source: 'Offline fixture', note: 'Fiscal years' }],
  } }))
  assert.match(html, /AI 研报未完成/)
  assert.match(html, /Offline fixture/)
  assert.match(html, /-50/)
  assert.match(html, /—/)
  assert.equal((html.match(/<rect /g) || []).length, 2)
  assert.match(html, /无估值数据/)
})

test('background job request keeps own model source and stable submission id', async () => {
  let sent
  const api = load('api/jobs.ts', {
    localStorage: { getItem: () => 'offline-user-token' },
    fetch: async (url, options) => { sent = { url, options }; return Response.json({ id: 'job-id' }, { status: 202 }) },
  })
  assert.deepEqual(await api.submitJob(result.request, 'personal', 'stable-request'), { id: 'job-id' })
  assert.equal(sent.url, '/v1/research/jobs')
  assert.equal(sent.options.headers.Authorization, 'Bearer offline-user-token')
  const body = JSON.parse(sent.options.body)
  assert.equal(body.source, 'personal')
  assert.equal(body.client_id, 'stable-request')
  assert.equal(body.api_key, undefined)
})
