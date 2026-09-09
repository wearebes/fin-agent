const assert = require('node:assert/strict')
const { test } = require('node:test')
const path = require('node:path')
const { buildSync } = require('esbuild')

const code = buildSync({
  entryPoints: [path.join(__dirname, '../src/store/workspace.ts')],
  bundle: true,
  platform: 'node',
  format: 'cjs',
  packages: 'external',
  write: false,
}).outputFiles[0].text

function loadWorkspace(data = new Map()) {
  const storage = {
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => data.set(key, value),
    removeItem: (key) => data.delete(key),
  }
  const module = { exports: {} }
  // Isolate storage without changing browser globals or writing real user history.
  new Function('require', 'module', 'exports', 'localStorage', code)(
    require, module, module.exports, storage,
  )
  return module.exports.useWorkspace
}

for (const [lang, projectName, title] of [
  ['zh', '我的工作区', '新研究'],
  ['en', 'My workspace', 'New research'],
]) {
  test(`defaults stay idempotent and localized (${lang})`, () => {
    const store = loadWorkspace()
    store.getState().setLang(lang)
    store.getState().ensureDefaults()
    const first = store.getState()
    store.getState().ensureDefaults()
    const state = store.getState()
    assert.equal(state.projects.length, 1)
    assert.equal(state.sessions.length, 1)
    assert.equal(state.projects[0].name, projectName)
    assert.equal(state.sessions[0].title, title)
    assert.equal(state.currentProjectId, first.currentProjectId)
    assert.equal(state.currentSessionId, first.currentSessionId)
  })
}

test('invalid selection repairs to first session; project selection uses most recent', () => {
  const store = loadWorkspace()
  const first = store.getState().createProject()
  const newer = store.getState().createSession(first.project.id)
  store.setState({
    currentProjectId: 'missing', currentSessionId: 'missing',
    sessions: [first.session, { ...newer, updatedAt: newer.updatedAt + 100 }],
  })
  store.getState().ensureDefaults()
  assert.equal(store.getState().currentSessionId, first.session.id)
  assert.equal(store.getState().selectProject(first.project.id), newer.id)
  store.getState().ensureDefaults()
  assert.equal(store.getState().currentSessionId, newer.id)
  assert.equal(store.getState().sessions.length, 2)
})

test('missing sessions are created once and orphaned sessions reset with no projects', () => {
  const store = loadWorkspace()
  const { project, session } = store.getState().createProject()
  store.getState().deleteSession(session.id)
  store.getState().ensureDefaults()
  assert.equal(store.getState().sessions.length, 1)
  assert.equal(store.getState().sessions[0].projectId, project.id)
  store.getState().deleteSession(store.getState().currentSessionId)
  const selected = store.getState().selectProject(project.id)
  assert.equal(store.getState().selectProject(project.id), selected)
  assert.equal(store.getState().sessions.length, 1)
  store.setState({ projects: [] })
  store.getState().ensureDefaults()
  assert.equal(store.getState().sessions.length, 1)
  assert.notEqual(store.getState().currentProjectId, project.id)
  assert.equal(store.getState().sessions[0].projectId, store.getState().currentProjectId)
})

test('deleting a project or session preserves unrelated history', () => {
  const store = loadWorkspace()
  const first = store.getState().createProject()
  const second = store.getState().createProject()
  for (const session of [first.session, second.session]) {
    store.getState().addMessage({
      sessionId: session.id, role: 'user', content: session.id, status: 'completed',
    })
  }
  store.getState().selectProject(first.project.id)
  store.getState().deleteProject(first.project.id)
  assert.deepEqual(store.getState().projects, [second.project])
  assert.equal(store.getState().currentProjectId, second.project.id)
  assert.equal(store.getState().currentSessionId, null)
  assert.deepEqual(store.getState().messages.map((m) => m.content), [second.session.id])
  store.getState().ensureDefaults()
  assert.equal(store.getState().currentSessionId, second.session.id)
  store.getState().deleteSession(second.session.id)
  assert.equal(store.getState().messages.length, 0)
  assert.equal(store.getState().currentSessionId, null)
  assert.equal(store.getState().projects.length, 1)
})

test('reload preserves persisted data and recovers only interrupted assistant messages', () => {
  const storage = new Map()
  const store = loadWorkspace(storage)
  store.getState().ensureDefaults()
  const sessionId = store.getState().currentSessionId
  for (const [role, status] of [
    ['assistant', 'running'], ['assistant', 'completed'], ['user', 'running'],
  ]) {
    store.getState().addMessage({ sessionId, role, status, content: 'kept' })
  }
  const before = store.getState()
  const restored = loadWorkspace(storage).getState()
  assert.deepEqual(restored.projects, before.projects)
  assert.deepEqual(restored.sessions, before.sessions)
  assert.equal(restored.currentSessionId, sessionId)
  assert.equal(restored.messages[0].status, 'failed')
  assert.match(restored.messages[0].error, /interrupted/)
  assert.equal(restored.messages[0].updatedAt, before.messages[0].updatedAt)
  assert.equal(before.messages[0].status, 'running')
  assert.deepEqual(restored.messages.slice(1), before.messages.slice(1))
})

test('drafts stay with their session and titles come from the first question without a model', () => {
  const storage = new Map()
  const store = loadWorkspace(storage)
  const first = store.getState().createProject()
  const second = store.getState().createSession(first.project.id)
  store.getState().updateSession(first.session.id, { draft: { question: 'Draft one', ticker: 'AAPL' } })
  store.getState().updateSession(second.id, { draft: { question: 'Draft two', ticker: 'MSFT' } })
  for (const content of ['  Apple\n cash flow  ', 'A later follow-up']) {
    store.getState().addMessage({ sessionId: first.session.id, role: 'user', status: 'completed', content })
  }
  const restored = loadWorkspace(storage).getState()
  assert.equal(restored.sessions[0].title, 'Apple cash flow')
  assert.deepEqual(restored.sessions.map((s) => s.draft.ticker), ['AAPL', 'MSFT'])
})
