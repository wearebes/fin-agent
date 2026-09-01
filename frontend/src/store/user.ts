import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { UserResponse } from '../api/auth'
import { apiGetMe } from '../api/auth'

export type ModelSource = 'default' | 'personal' | 'codex'

interface UserState {
  token: string | null
  user: UserResponse | null
  modelSource: ModelSource
  setModelSource: (source: ModelSource) => void
  setAuth: (token: string, user: UserResponse) => void
  clearAuth: () => void
  fetchMe: () => Promise<void>
  updateUser: (user: UserResponse) => void
}

export const useUserStore = create<UserState>()(
  persist(
    (set, get) => ({
      token: null,
      user: null,
      modelSource: 'default',
      setModelSource: (modelSource) => set({ modelSource }),
      setAuth: (token, user) => {
        localStorage.setItem('fin-agent-token', token)
        set({ token, user, modelSource: get().user?.id === user.id ? get().modelSource : 'default' })
      },
      clearAuth: () => {
        localStorage.removeItem('fin-agent-token')
        set({ token: null, user: null, modelSource: 'default' })
      },
      fetchMe: async () => {
        const { token } = get()
        if (!token) return
        try {
          const user = await apiGetMe()
          set({ user })
        } catch {
          get().clearAuth()
        }
      },
      updateUser: (user) => set({ user }),
    }),
    {
      name: 'fin-agent-user-v1',
      partialize: (state) => ({ token: state.token, user: state.user, modelSource: state.modelSource }),
    }
  )
)
