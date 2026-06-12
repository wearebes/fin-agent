// Manual mirror of `SkillDescriptor` — the wire model the API actually
// serves (src/fin_agent/interfaces/api/router.py), NOT the richer internal
// `Skill`/`SkillTrigger` domain model in src/fin_agent/skills/__init__.py.
// The router flattens `trigger.slash` into a plain string and hoists
// `aliases` to the top level; keep this mirror in sync with `SkillDescriptor`,
// not the domain model. This is a pure catalog projection — the backend
// deliberately never serves manifest body text here, so there is nothing
// injectable to keep out of the client bundle.

export interface Skill {
  name: string
  // Primary slash trigger INCLUDING the leading slash, e.g. "/valuation".
  trigger: string
  aliases: string[]
  description: string
  input_schema: Record<string, unknown>
}

interface SkillsResponse {
  skills: Skill[]
}

/**
 * GET /v1/skills — anonymous catalog listing.
 *
 * Used by the composer's `/`-triggered picker to resolve names into
 * descriptors (for filtering/display only). The chosen `Skill.name` is later
 * sent back as `ResearchRequest.selected_skill`, an opaque key the backend
 * resolves server-side — the client never sees or sends prompt text.
 */
export async function listSkills(): Promise<Skill[]> {
  const res = await fetch('/v1/skills')
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(text || `HTTP ${res.status} ${res.statusText}`)
  }
  const payload = (await res.json()) as SkillsResponse
  return payload.skills ?? []
}

// --- Management API (the /user/skills admin page) -------------------------
// These mirror the SkillDetail / SkillMutationResult models the router serves
// from src/fin_agent/interfaces/api/router.py. Unlike the anonymous catalog
// above, `details` carries `source`/`version` so the UI can lock builtins and
// only offer external skills for deletion.

/** Catalog entry enriched with provenance, for the admin listing. */
export interface SkillDetail extends Skill {
  source: 'builtin' | 'external'
  version: string
}

/** Shared result of install/upload/delete/reload — `total_skills` always set. */
export interface SkillMutationResult {
  total_skills: number
  name?: string | null
  source?: string | null
  overwritten?: boolean | null
}

/** Throw an Error carrying the FastAPI `{detail}` message when present. */
async function ensureOk(res: Response): Promise<void> {
  if (res.ok) return
  let detail = ''
  try {
    const body = (await res.json()) as { detail?: unknown }
    if (typeof body.detail === 'string') detail = body.detail
  } catch {
    detail = await res.text().catch(() => '')
  }
  throw new Error(detail || `HTTP ${res.status} ${res.statusText}`)
}

/** GET /v1/skills/details — full listing with builtin/external provenance. */
export async function listSkillsWithSource(): Promise<SkillDetail[]> {
  const res = await fetch('/v1/skills/details')
  await ensureOk(res)
  const payload = (await res.json()) as { skills?: SkillDetail[] }
  return payload.skills ?? []
}

/** POST /v1/skills/install — download and install a SKILL.md from a URL. */
export async function installSkillFromUrl(url: string): Promise<SkillMutationResult> {
  const res = await fetch('/v1/skills/install', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  })
  await ensureOk(res)
  return (await res.json()) as SkillMutationResult
}

/** POST /v1/skills/upload — install from an uploaded SKILL.md file. */
export async function uploadSkill(file: File): Promise<SkillMutationResult> {
  const form = new FormData()
  form.append('file', file)
  // Deliberately no Content-Type header: the browser must set the multipart
  // boundary itself, otherwise the backend cannot parse the upload.
  const res = await fetch('/v1/skills/upload', { method: 'POST', body: form })
  await ensureOk(res)
  return (await res.json()) as SkillMutationResult
}

/** DELETE /v1/skills/{name} — remove an external skill (builtins are 403). */
export async function deleteSkill(name: string): Promise<SkillMutationResult> {
  const res = await fetch(`/v1/skills/${encodeURIComponent(name)}`, {
    method: 'DELETE',
  })
  await ensureOk(res)
  return (await res.json()) as SkillMutationResult
}

/** POST /v1/skills/reload — re-scan the skill dirs (for hand-dropped files). */
export async function reloadSkills(): Promise<SkillMutationResult> {
  const res = await fetch('/v1/skills/reload', { method: 'POST' })
  await ensureOk(res)
  return (await res.json()) as SkillMutationResult
}
