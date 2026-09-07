import type { WorkspaceSnapshot } from '../store/workspace'

export interface LocalSetupStatus {
  configured: boolean
  workspace_persistent: boolean
  auth_persistent: boolean
}

export interface LocalSetupInput {
  api_key?: string
  model: string
  base_url?: string
}

async function localRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options.headers ?? {}) },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(body?.detail || `HTTP ${response.status}`)
  }
  return response.json() as Promise<T>
}

export function getLocalSetupStatus() {
  return localRequest<LocalSetupStatus>('/v1/local/setup/status')
}

export function saveLocalSetup(input: LocalSetupInput) {
  return localRequest<LocalSetupStatus>('/v1/local/setup', {
    method: 'POST', body: JSON.stringify(input),
  })
}

export async function getLocalWorkspace(): Promise<WorkspaceSnapshot | null> {
  const response = await fetch('/v1/local/workspace')
  if (!response.ok) return null
  const body = await response.json() as { payload?: WorkspaceSnapshot } | null
  return body?.payload ?? null
}

export function saveLocalWorkspace(snapshot: WorkspaceSnapshot) {
  return localRequest('/v1/local/workspace', {
    method: 'PUT', body: JSON.stringify({ payload: snapshot }),
  })
}
