export interface HealthInfo {
  ok: boolean
  mode: string
  time: string
}

export type ReasoningEffort = 'low' | 'medium' | 'high' | 'xhigh' | 'max'

export interface SettingsStatus {
  secrets: Record<string, boolean>
  prime_models_synced: boolean
}

export interface Settings {
  schema_version: number
  revision: number
  app: { host: string; port: number; mode: string; data_dir: string }
  brain: {
    runtime: string
    executable: string
    model_id: string
    reasoning_effort: ReasoningEffort
    auth_mode: string
  }
  executor: {
    runtime: string
    executable: string
    model_id: string
    reasoning_effort: ReasoningEffort
  }
  prime: {
    executable: string
    llm_profile_id: string
    automatic_refine: boolean
    subagents_enabled: boolean
  }
  llm_profiles: LlmProfile[]
  playground: { base_url: string; token_secret_ref: string }
  bohrium: {
    executable: string
    access_key_secret_ref: string
    project_id: string | null
    host_overrides: Record<string, string>
  }
  policy: {
    science_compute: string
    default_authorization: string
    allow_formal_submission: boolean
  }
  run_defaults: {
    max_active_runs: number
    max_trials: number
    max_brain_reviews: number
    max_run_minutes: number
    max_model_turns: number
    max_jobs: number
    max_submissions: number
  }
  memory: {
    root: string
    max_global_entries: number
    max_challenge_entries: number
    max_injected_characters: number
  }
  _status?: SettingsStatus
}

export interface LlmProfile {
  label: string
  protocol: string
  base_url: string
  model_id: string
  secret_ref: string
  pricing?: { input_per_million?: number; output_per_million?: number } | null
}

export interface ConnectionHealth {
  installed: boolean | null
  authenticated: boolean | null
  detail: string
  version: string | null
  capabilities: string[]
}

export interface ConnectionTestResult {
  status: string
  health: ConnectionHealth
}

export interface ChallengeSummary {
  id: string
  platform_challenge_id: string | null
  origin: string
  title: string
  contract_status: string
  imported_at: string
  is_demo: boolean
}

export interface ChallengeDetail extends ChallengeSummary {
  content?: string
}

export interface TrialSummary {
  id: string
  goal: string
  status: string
  created_at: string
}

export interface RunBudget {
  brain_reviews_used: number
  max_brain_reviews: number
  model_turns: { limit: number; known_cost: number | null; unknown_cost: boolean | number }
  max_submissions: number
}

export type RunPhase =
  | 'created'
  | 'running'
  | 'pausing'
  | 'paused'
  | 'blocked'
  | 'finished'
  | 'failed'
  | 'cancelled'

export interface RunSummary {
  id: string
  challenge_id: string
  mode: string
  phase: RunPhase
  state_version: number
  created_at?: string
}

export interface RunDetail extends RunSummary {
  intention: string | null
  block_reason: string | null
  current_trial_id: string | null
  trials: TrialSummary[]
  budget: RunBudget | null
  config_snapshot: unknown
}

export interface RunEvent {
  event_id: string
  seq: number
  occurred_at: string
  source: 'brain' | 'prime' | 'controller' | 'user' | 'demo' | string
  type: string
  trial_id: string | null
  payload: Record<string, unknown>
}

export interface Checkpoint {
  id?: string
  trial_id?: string | null
  report: string
  evidence_refs: string[]
  created_at?: string
}

export interface ExperienceFrontmatter {
  id: string
  title: string
  scope: 'global' | 'challenge'
  challenge_id: string | null
  status: 'candidate' | 'active' | 'retired'
  evidence_status: 'hypothesis' | 'observed' | 'validated' | 'contradicted'
  kind: 'heuristic' | 'procedure' | 'failure' | 'platform'
  tags: string[]
  applicability: string
  evidence_refs: string[]
  expires_at: string | null
}

export interface ExperienceItem extends ExperienceFrontmatter {
  file: string
  current_hash: string
  revision_hash: string
  updated_at: string
  updated_by: string
}

export interface ExperienceRevision {
  revision_hash: string
  parent_hash: string | null
  operator: string
  reason: string | null
  created_at: string
}

export interface ExperienceDetail {
  id: string
  file: string
  frontmatter: ExperienceFrontmatter
  body_md: string
  current_hash: string
  revisions: ExperienceRevision[]
}

export interface RevisionConflictDetails {
  current_hash: string
  current_content: string
  your_content: string
}
