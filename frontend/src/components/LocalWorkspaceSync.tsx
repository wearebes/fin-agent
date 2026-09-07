import { useEffect } from 'react'
import { getLocalWorkspace, saveLocalWorkspace } from '../api/local'
import { useWorkspace, type WorkspaceSnapshot } from '../store/workspace'

function snapshot(): WorkspaceSnapshot {
  const state = useWorkspace.getState()
  return {
    projects: state.projects,
    sessions: state.sessions,
    messages: state.messages,
    currentProjectId: state.currentProjectId,
    currentSessionId: state.currentSessionId,
    lang: state.lang,
    showThinking: state.showThinking,
    planMode: state.planMode,
  }
}

/** Mirrors the local browser cache into the user's SQLite file. */
export default function LocalWorkspaceSync() {
  useEffect(() => {
    let ready = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const unsubscribe = useWorkspace.subscribe(() => {
      if (!ready) return
      if (timer) clearTimeout(timer)
      timer = setTimeout(() => { void saveLocalWorkspace(snapshot()) }, 600)
    })

    void getLocalWorkspace().then((saved) => {
      if (saved?.projects?.length) useWorkspace.getState().replaceWorkspace(saved)
    }).finally(() => {
      ready = true
      void saveLocalWorkspace(snapshot())
    })

    return () => {
      if (timer) clearTimeout(timer)
      unsubscribe()
    }
  }, [])

  return null
}
