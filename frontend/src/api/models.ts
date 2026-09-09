import { request } from './auth'

export type ModelProtocol = 'openai' | 'anthropic'
export type TokenParameter = 'max_tokens' | 'max_completion_tokens'
export interface ModelConnection {
  base_url: string
  model: string
  protocol: ModelProtocol
  token_parameter: TokenParameter
  expires_at: string
}
export type ConnectionInput = Omit<ModelConnection, 'expires_at'> & { api_key: string }
export const connectionPath = '/v1/user/model-connection'

export interface ModelAccess {
  local_codex: boolean
  system_model: boolean
  commercial_mode: boolean
}
export const getModelAccess = () => request<ModelAccess>('/v1/user/model-access')
export const getCodexStatus = () => request<{ ready: boolean; model: string }>('/v1/user/codex')
export const testCodexConnection = () => request<{
  ok: boolean; model: string; text: string; input_tokens: number | null; output_tokens: number | null
}>('/v1/user/codex/test', { method: 'POST' })

export const getModelConnection = () => request<{ connection: ModelConnection | null }>(connectionPath)
export const saveModelConnection = (input: ConnectionInput) => request<{ connection: ModelConnection }>(connectionPath, {
  method: 'PUT', body: JSON.stringify(input),
})
export const disconnectModel = () => request<void>(connectionPath, { method: 'DELETE' })
export const testModelConnection = () => request<{ ok: boolean }>(`${connectionPath}/test`, { method: 'POST' })

export async function modelConnectionOptions(): Promise<{ allowed_hosts: string[] }> {
  const response = await fetch(`${connectionPath}/options`, { cache: 'no-store' })
  if (response.status === 404 || response.status === 405) {
    throw new Error('后端尚未启用模型设置，请启动新版后端。 / Start the updated backend to enable model settings.')
  }
  if (!response.ok) throw new Error('无法读取模型设置服务。 / Model settings service unavailable.')
  return response.json()
}
