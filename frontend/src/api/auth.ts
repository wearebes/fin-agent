export interface UserResponse {
  id: string
  username: string
  email: string
  display_name: string
  avatar_url: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  user: UserResponse
}

export interface RegisterInput {
  username: string
  email: string
  password: string
  display_name: string
}

export interface LoginInput {
  login_name: string
  password: string
}

export interface UpdateProfileInput {
  display_name?: string
  avatar_url?: string
}

export interface ChangePasswordInput {
  old_password: string
  new_password: string
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> || {}),
  }
  const token = localStorage.getItem('fin-agent-token')
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  const res = await fetch(path, { ...options, headers })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json()
      detail = body.detail || detail
    } catch {}
    throw new Error(detail)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export async function apiRegister(input: RegisterInput): Promise<TokenResponse> {
  return request<TokenResponse>('/v1/auth/register', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export async function apiLogin(input: LoginInput): Promise<TokenResponse> {
  return request<TokenResponse>('/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export async function apiGetMe(): Promise<UserResponse> {
  return request<UserResponse>('/v1/auth/me')
}

export async function apiUpdateProfile(input: UpdateProfileInput): Promise<UserResponse> {
  return request<UserResponse>('/v1/auth/profile', {
    method: 'PATCH',
    body: JSON.stringify(input),
  })
}

export async function apiChangePassword(input: ChangePasswordInput): Promise<{ detail: string }> {
  return request<{ detail: string }>('/v1/auth/change-password', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}
