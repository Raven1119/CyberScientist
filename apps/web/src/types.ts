export interface HealthInfo {
  ok: boolean
  mode: string
  time: string
}

export type ReasoningEffort = 'low' | 'medium' | 'high' | 'xhigh' | 'max'

export interface SettingsStatus {
  secrets: Record<string, boolean>
  prime_authentication: string
}

export interface SolverEntry extends ModelChoice { id: string; name: string; note?: string }

export interface Settings {
  submission_transport?: 'cli' | 'api'
  codex_fast_mode?: boolean
  submission_policy?: { same_topic_minutes: number; cross_topic_minutes: number; cross_topic_limit: number }
  features?: Record<string, boolean>
  schema_version: number
  revision: number
  app: { host: string; port: number; mode: string; data_dir: string }
  brain: {
    fast_mode?: boolean
    provider?: string
    runtime: string
    executable: string
    model_id: string
    reasoning_effort: ReasoningEffort
    auth_mode: string
  }
  executor: {
    fast_mode?: boolean
    provider?: string
    runtime: string
    executable: string
    model_id: string
    reasoning_effort: ReasoningEffort
  }
  reviewer?: ModelChoice & { executable?: string }
  post_review?: ModelChoice & { executable?: string }
  solver_roster?: SolverEntry[]
  model_pricing?: Record<string, unknown>
  harvest?: { score_threshold: number; experiments_done_at_leader: boolean; deadline_check_hours: number; safety_margin_minutes?: number }
  prime: {
    executable: string
    llm_profile_id: string
    automatic_refine: boolean
    subagents_enabled: boolean
  }
  llm_profiles: LlmProfile[]
  playground: { cli_executable?: string; base_url: string; token_secret_ref: string }
  bohrium: {
    executable: string
    wenyon_executable: string
    wenyon_home: string
    access_key_secret_ref: string
    project_id: string | null
    host_overrides: Record<string, string | Record<string, string>>
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
    stall_seconds: number
    max_brain_wait_seconds: number
    pi_review_interval_seconds?: number
    brain_review_timeout_seconds: number
    rate_limit_max_seconds: number
  }
  shadow: {
    enabled: boolean
    min_interval_seconds: number
    max_interval_seconds: number
    max_reviews: number
  }
  mailbox: {
    platform: string
    submission_limit: number
  }
  memory: {
    root: string
    max_global_entries: number
    max_challenge_entries: number
    max_injected_characters: number
  }
  skills: { always_on: string[] }
  deepseek_fallback?: { after_minutes: number; solver_id: string }
  resources?: { provider_sessions: Record<string, number>; max_concurrent_jobs: number | null; max_concurrent_sandboxes: number | null }
  _status?: SettingsStatus
}

export interface LlmProfile {
  id: string
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
  capabilities: Record<string, boolean> | string[]
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
  model_config?: { brain: ModelChoice; executor: ModelChoice }
  platform_snapshot?: {
    status?: string | null
    roundEndAt?: string | null
    scoring?: { grader_name?: string | null; strategy?: string | null } | null
    fetched_at?: string
  } | null
}

export interface ModelChoice {
  fast_mode?: boolean
  provider?: string
  note?: string
  runtime: string
  model_id: string
  reasoning_effort: ReasoningEffort
}

export interface RunOverview {
  id: string
  challenge_id: string
  challenge_title: string
  phase: RunPhase
  gate: string | null
  current_trial_id: string | null
  latest_score: number | null
  score_confidence: 'provisional' | 'confirmed' | null
  job_count: number
  sandbox_count: number
  needs_attention: boolean
  attention_reason: string | null
}

export interface SkillInfo {
  id: string
  name: string
  description: string
  source: string
  always_on: boolean
  bound: boolean
}

export interface SkillCatalogResponse {
  skills: SkillInfo[]
  always_on: string[]
  bound: string[]
}

export interface TrialSummary {
  id: string
  goal: string
  status: string
  created_at: string
  delivered?: boolean
}

export interface RunBudget {
  unlimited_resources?: boolean
  brain_reviews_used: number
  max_brain_reviews: number | null
  trials_used: number
  max_trials: number | null
  run_minutes_limit: number
  run_minutes_exceeded: boolean
  model_turns: { limit: number | null; known_cost: number | null; unknown_cost: boolean | number }
  max_submissions: number
  max_jobs: number | null
  max_sandboxes: number | null
  max_sandbox_minutes: number | null
  allow_sandbox_gpu: boolean
}

export type RunPhase =
  | 'created'
  | 'waiting_score'
  | 'running'
  | 'pausing'
  | 'paused'
  | 'blocked'
  | 'recovering'
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
  objective_md?: string | null
  objective_status?: string
  end_reason?: string | null
  gate?: string
  pending_action_json?: string | null
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
  kind: 'heuristic' | 'procedure' | 'failure' | 'platform' | 'environment' | 'strategy'
  audience: 'brain' | 'executor' | 'both'
  tags: string[]
  applicability: string
  evidence_refs: string[]
  expires_at: string | null
}

export interface ExperienceItem extends ExperienceFrontmatter {
  revision_id: string
  active_revision_id: string | null
  review_note: string | null
  file: string
  current_hash: string
  revision_hash: string
  updated_at: string
  updated_by: string
}

export interface ExperienceRevision {
  revision_id: string
  revision_hash: string
  parent_hash: string | null
  operator: string
  reason: string | null
  created_at: string
}

export interface ExperienceDetail {
  revision_id: string
  active_revision_id: string | null
  id: string
  file: string
  frontmatter: ExperienceFrontmatter
  body_md: string
  current_hash: string
  revisions: ExperienceRevision[]
  adoptions?: { run_id: string; trial_id: string | null; revision_id: string; adopted_seq: number; semantics: string }[]
}

export interface RevisionConflictDetails {
  current_hash: string
  current_content: string
  your_content: string
}

export type SupervisionGate = 'open' | 'yielding' | 'waiting_brain' | 'stopped'

export type GuidanceStatus =
  | 'queued'
  | 'sending'
  | 'sent'
  | 'acknowledged'
  | 'unknown'
  | 'rejected'
  | 'superseded'
  | 'invalidated'

export interface SupervisionWatchItem {
  id: string
  hypothesis_md: string
  evidence_needed_md: string
  intervene_when_md: string
  evidence_refs: string[]
}

export interface SupervisionPendingRequest {
  id: string
  source: string
  blocking: boolean
  status: string
  trigger: string
  created_at: string
}

export interface SupervisionGuidance {
  id: string
  source?: string
  kind: string
  intent: string
  status: GuidanceStatus | string
  text_md: string
  target_trial_id: string | null
  ack_disposition: string | null
  created_at: string
}

export interface SupervisionStatus {
  enabled: number
  shadow_epoch: number
  covered_seq: number
  evidence_revision: number
  reviews_used: number
  max_reviews: number | null
  private_note_md: string
  watchlist: SupervisionWatchItem[]
  last_review_at: string | null
  degraded: number
  degrade_reason: string | null
  brain_busy: boolean
  gate: SupervisionGate
  executor_busy: boolean
  pending_requests: SupervisionPendingRequest[]
  guidance: SupervisionGuidance[]
  research_answers?: {
    id: string; status: string; trigger: string; answer_md: string | null
    native_form: string; guidance_id: string | null; delivery_status: string | null
    delivery_channel: string | null; ack_disposition: string | null
    evidence_refs: string[]; error: string | null; created_at: string
  }[]
  trace_reads?: {
    seq: number; review_id: string; action: string; ref?: string | null
    source_seq?: number | null; through_seq: number; recorded_at: string
  }[]
  last_wake?: { trigger: string; source: string; created_at: string } | null
  latest_seq: number
}

export interface ReviewRequestResult {
  review_id: string
  status: string
}

export interface Mailbox {
  claim_status?: 'pending' | 'confirmed' | 'unknown'
  platform_account_id?: string | null
  operator_id?: string | null
  id: string
  role: 'harvest' | 'experiment'
  email: string
  platform: string
  status: 'active' | 'disabled'
  submission_limit: number
  is_demo: number
  secret_configured: boolean
  created_at: string
}

export interface MailboxList {
  items: Mailbox[]
  platform: string
  platform_is_demo: boolean
}

export interface MailboxUsage {
  target_platform?: string
  target_origin?: string
  mailbox_id: string
  email: string
  role: 'harvest' | 'experiment'
  platform_challenge_id: string
  challenge_title: string
  used: number
  limit: number
}

export interface Submission {
  id: string
  run_id: string
  trial_id: string | null
  mailbox_id: string
  mailbox_email?: string
  package_path: string
  package_sha256: string
  source_package_sha256?: string | null
  source_submission_id?: string | null
  variant_of?: string | null
  replay_of?: string | null
  science_artifact_match?: 0 | 1 | null
  admission_json?: string | null
  status: string
  score: number | null
  score_status: 'unknown' | 'pending' | 'scored' | 'failed'
  platform_status?: string | null
  score_confidence?: 'provisional' | 'confirmed' | null
  score_anomaly?: string | null
  scorecard_consistent?: 0 | 1 | null
  displayScore?: number | null
  harbor_score?: number | null
  trace_score?: number | null
  harbor_reward?: number | null
  trace_decision?: string | null
  trace_factor?: number | null
  scoring_source?: string | null
  score_is_final?: number | null
  scoring_minutes?: number | null
  receipt_details?: {deductions?: {code: string; score_effect?: number}[]; missing_evidence?: unknown[]}
  prediction_md?: string | null
  prediction_verdict?: 'confirmed' | 'refuted' | 'unclear' | null
  prediction_note_md?: string | null
  is_highest?: boolean
  warnings?: string[]
  is_harvest: number
  platform_ref: string | null
  error: string | null
  created_at: string
  submitted_at: string | null
  scored_at: string | null
  platform_feedback?: Record<string, { response: unknown; recorded_at: string }>
}
