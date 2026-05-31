# fin-agent frontend (Phase 1)

React + TypeScript + Vite workspace for the fin-agent research platform.

## Develop

```bash
npm install
npm run dev          # http://localhost:5173 (proxies /v1 and /healthz to :8000)
```

Run the backend separately so research requests resolve:

```bash
fin-agent api --reload   # http://localhost:8000
```

## Other scripts

```bash
npm run typecheck    # tsc --noEmit
npm run build        # type-check + production build into dist/
npm run preview      # serve the production build locally
```

## Scope (Phase 1)

A stable, verifiable single-shot research workspace:

- Projects → Sessions hierarchy, persisted to `localStorage`
  (Zustand, key `fin-agent-workspace-v1`).
- One-question-one-answer research flow against `POST /v1/research/runs`
  (a long blocking synchronous request — no polling, no SSE).
- Full `RunResult` rendering: status, providers, planned stages,
  markdown report, evidence, execution trace.
- Quant page: starfield + feature cards (visual migration only).
- Chinese / English toggle.

Out of scope for Phase 1: real multi-turn, streaming, backend history
tables, project rename/delete, cross-device sync, new financial charts.

When `frontend/dist` exists, the FastAPI app serves it at `/`. Removing
`dist/` falls back to the legacy `static/index.html`.
