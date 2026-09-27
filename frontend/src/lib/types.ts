// Mirrors backend/app/schemas — keep in sync. JSON is snake_case end to end.

export type Stage = 'new' | 'shortlisted' | 'cv_ready' | 'ready' | 'done' | 'interview' | 'closed'
export type Route = 'undecided' | 'cold_email' | 'web_apply'
export type ContactTier = 'apollo_dump' | 'lookup_queued' | 'lookup_found' | 'none'
export type Source = 'adzuna' | 'remotive' | 'arbeitnow' | 'wttj' | 'boards' | 'bayt'

export interface CompanyBoard {
  ats: 'greenhouse' | 'lever' | 'ashby' | 'workable' | 'smartrecruiters'
  token: string
  company: string
}
export type RemoteType = 'remote' | 'hybrid' | 'onsite' | 'unknown'
export type FitBand = 'strong' | 'good' | 'fair' | 'weak' | 'failed' | 'pending'
export type CloseReason = 'dismissed' | 'rejected' | 'withdrawn' | 'no_response' | 'offer'
export type ExperienceKind = 'job' | 'project' | 'skill' | 'education' | 'certification' | 'volunteering'

export interface CompanyRef {
  id: number
  name: string
  contacted_at: string | null
}

export type Confidence = 'high' | 'medium' | 'low'
export type UserLabel = 'good' | 'maybe' | 'no'
export type DescriptionLevel = 'full' | 'summary' | 'snippet'

export interface FitBrief {
  score: number | null
  band: FitBand
  status: 'ok' | 'failed' | 'pending'
  confidence: Confidence
  hard_flag: boolean
  flag_count: number
  stale: boolean
}

export type Dimension =
  | 'role_match'
  | 'skills_match'
  | 'seniority_fit'
  | 'location_eligibility'
  | 'language_requirements'

export interface SubScoreOut {
  score: number
  reason: string
  evidence: string
  evidence_verified: boolean
  adjusted_from?: number
}

export interface RedFlagOut {
  type: string
  text: string
  evidence: string
  evidence_verified: boolean
  severity: 'hard' | 'soft'
}

export interface FitDetail extends FitBrief {
  sub_scores: Partial<Record<Dimension, SubScoreOut>>
  red_flags: RedFlagOut[]
  strengths: string[]
  gaps: string[]
  summary: string
  model: string
  prompt_version: string | null
  error: string | null
  duration_ms: number | null
  created_at: string
}

export interface ApplicationBrief {
  id: number
  stage: Stage
  stage_label: string
  route: Route
  contact_tier: ContactTier
  close_reason: CloseReason | null
  stage_changed_at: string
}

export interface JobListItem {
  id: number
  description_level: DescriptionLevel
  user_label: UserLabel | null
  title: string
  company: CompanyRef
  source: Source
  url: string
  location: string
  country: string | null
  remote_type: RemoteType
  salary_text: string | null
  posted_at: string | null
  discovered_at: string
  fit: FitBrief | null
  application: ApplicationBrief
  duplicate_of_id: number | null
  company_contacted: boolean
}

export interface JobList {
  items: JobListItem[]
  total: number
}

export interface Contact {
  id: number
  company_id: number
  full_name: string
  title: string | null
  email: string | null
  linkedin_url: string | null
  source: 'apollo_dump' | 'apollo_lookup' | 'manual'
}

export interface TimelineEvent {
  id: number
  kind: string
  from_stage: Stage | null
  to_stage: Stage | null
  message: string | null
  payload: Record<string, unknown>
  at: string
}

export interface RelatedJob {
  id: number
  title: string
  source: Source
  url: string
  stage: Stage
  stage_label: string
}

export interface CVBrief {
  id: number
  version: number
  status: CVStatus
  page_count: number | null
  generator_model: string
  created_at: string
  updated_at: string
}

export interface DraftBrief {
  id: number
  subject: string
  body: string
  status: DraftStatus
  edited: boolean
  contact_name: string | null
  created_at: string
  updated_at: string
}

export interface JobDetail extends JobListItem {
  description: string
  fit_detail: FitDetail | null
  notes: string
  contact: Contact | null
  company_contacts: number
  other_jobs_at_company: RelatedJob[]
  duplicates: RelatedJob[]
  cv_versions: CVBrief[]
  drafts: DraftBrief[]
  events: TimelineEvent[]
  allowed_stages: Stage[]
}

export interface PipelineCard {
  application_id: number
  job_id: number
  title: string
  company_name: string
  source: Source
  location: string
  remote_type: RemoteType
  fit: FitBrief | null
  stage: Stage
  stage_label: string
  route: Route
  contact_tier: ContactTier
  close_reason: CloseReason | null
  stage_changed_at: string
  updated_at: string
  allowed_stages: Stage[]
}

export interface ApplicationPatch {
  stage?: Stage
  close_reason?: CloseReason
  route?: Route
  notes?: string
}

// CV
export type CVStatus = 'draft' | 'approved' | 'superseded'

export interface CVEntry {
  title: string
  org: string
  location: string
  dates: string
  bullets: string[]
}

export interface CVSkillGroup {
  group: string
  items: string[]
}

export interface CVContent {
  name: string
  headline: string
  contact: string[]
  summary: string
  experience: CVEntry[]
  projects: CVEntry[]
  skills: CVSkillGroup[]
  education: CVEntry[]
}

export interface CVVersion {
  id: number
  application_id: number
  version: number
  status: CVStatus
  content: CVContent
  page_count: number | null
  generator_model: string
  created_at: string
  updated_at: string
}

export interface CVStudio {
  application_id: number
  job_id: number
  job_title: string
  company_name: string
  stage: Stage
  route: Route
  has_contact: boolean
  versions: CVVersion[]
}

export interface CVApproveResult {
  version: CVVersion
  stage: Stage
  route: Route
  next_step: 'draft_email' | 'mark_ready_to_apply'
}

// Outreach
export type DraftStatus = 'draft' | 'approved' | 'rejected' | 'queued' | 'sent' | 'failed'

export interface Draft {
  id: number
  application_id: number
  job_id: number
  job_title: string
  company_name: string
  fit: FitBrief | null
  contact: { id: number; full_name: string; title: string | null; email: string | null } | null
  subject: string
  body: string
  status: DraftStatus
  edited: boolean
  model: string
  cv_version: number | null
  created_at: string
  updated_at: string
}

export type QueueStatus = 'idle' | 'running' | 'paused'

export interface QueueItem {
  id: number
  position: number
  status: 'pending' | 'sending' | 'sent' | 'failed' | 'cancelled'
  scheduled_at: string | null
  sent_at: string | null
  error: string | null
  draft_id: number
  job_id: number
  subject: string
  contact_name: string | null
  contact_email: string | null
  company_name: string
}

export interface Queue {
  status: QueueStatus
  interval_minutes: number
  max_items: number
  next_send_at: string | null
  counts: { pending: number; sent: number; failed: number }
  items: QueueItem[]
}

// Experience
export interface ExperienceInput {
  kind: ExperienceKind
  title: string
  org: string | null
  location: string | null
  start_date: string | null
  end_date: string | null
  summary: string | null
  bullets: string[]
  tags: string[]
  is_active: boolean
}

export interface ExperienceItem extends ExperienceInput {
  id: number
  position: number
  is_placeholder: boolean
  updated_at: string
}

// Contacts
export interface CompanyListItem {
  id: number
  name: string
  domain: string | null
  contact_count: number
  open_jobs: number
  contacted_at: string | null
}

export interface CompanyDetail extends CompanyListItem {
  website: string | null
  contacts: Contact[]
  jobs: RelatedJob[]
}

export interface ImportPreview {
  filename: string
  total_rows: number
  columns: string[]
  mapping: Record<string, string | null>
  sample: Record<string, string>[]
}

export interface ImportResult {
  created: number
  updated: number
  skipped: number
  mock: boolean
}

export interface LookupQueue {
  daily_cap: number
  used_today: number
  items: {
    application_id: number
    job_id: number
    job_title: string
    company_name: string
    fit: number | null
    queued_at: string
  }[]
}

// Settings
export type RunStatus = 'pending' | 'running' | 'success' | 'partial' | 'failed' | 'skipped'

export interface FilteredSample {
  title: string
  company: string
  location: string
  reason: string
  url: string
}

export interface SourceRun {
  id: number
  discovery_run_id: number | null
  source: Source
  status: RunStatus
  started_at: string
  finished_at: string | null
  fetched_count: number
  kept_count: number
  filtered_count: number
  new_count: number
  updated_count: number
  duplicate_count: number
  error: string | null
  details: {
    requests?: number
    warnings?: string[]
    reasons?: Record<string, number>
    samples?: FilteredSample[]
    dry_run?: boolean
    /** Company boards source: board label → job count, or an error message. */
    boards?: Record<string, string | number>
  }
}

export type RemoteScope = 'anywhere' | 'europe' | 'targets'

export interface Country {
  code: string
  name: string
  region: string
}

export interface SearchProfile {
  name: string
  roles: string[]
  keywords: string[]
  excluded_keywords: string[]
  locations: string[]
  remote_policy: 'any' | 'remote_ok' | 'remote_only'
  remote_scope: RemoteScope
  min_fit_score: number
  max_age_days: number
}

export interface SettingsView {
  // Values are free-form JSON per key (see backend fixtures.SETTINGS); screens narrow them.
  values: Record<string, Record<string, unknown>>
  smtp_password_configured: boolean
  database_path: string
  last_runs: SourceRun[]
  next_run_at: string | null
}

export interface DiscoveryRun {
  id: number
  trigger: 'manual' | 'scheduled' | 'test'
  status: RunStatus
  started_at: string
  finished_at: string | null
  totals: Partial<Record<'fetched' | 'kept' | 'filtered' | 'new' | 'updated' | 'duplicate' | 'failed', number>>
  sources: SourceRun[]
}

export interface DiscoveryStatus {
  running: boolean
  run: DiscoveryRun | null
}

export interface SourceInfo {
  source: Source
  name: string
  enabled: boolean
  configured: boolean
  config_hint: string | null
  cooldown_hours: number
  cooldown_remaining_minutes: number | null
  last_run: SourceRun | null
  /** Target countries (search profile) this source cannot search. */
  unsupported_countries: string[]
}

export interface SampleJob {
  title: string
  company: string
  location: string
  remote_type: RemoteType
  url: string
  reason: string | null
}

export interface SourceTestResult {
  source: Source
  fetched: number
  kept: number
  filtered: number
  requests: number
  reasons: Record<string, number>
  warnings: string[]
  kept_samples: SampleJob[]
  filtered_samples: SampleJob[]
}

// Today / meta
export interface Today {
  new_high_fit: JobListItem[]
  new_high_fit_total: number
  cvs_to_review: {
    application_id: number
    job_id: number
    job_title: string
    company_name: string
    version: number
    created_at: string
  }[]
  drafts_to_approve: {
    draft_id: number
    job_id: number
    job_title: string
    company_name: string
    contact_name: string | null
    created_at: string
  }[]
  ready_to_apply: PipelineCard[]
  interviews: PipelineCard[]
  queue: {
    status: QueueStatus
    next_send_at: string | null
    pending: number
    sent: number
    interval_minutes: number
  }
  last_runs: SourceRun[]
  min_fit_score: number
}

export interface NavCounts {
  discover_new: number
  pipeline_active: number
  outreach_review: number
  queue_pending: number
}

export interface SearchHit {
  kind: 'job' | 'company' | 'contact'
  id: number
  title: string
  subtitle: string
  href: string
}

export interface ScoringStatus {
  running: boolean
  blocked: string | null
  queued: number
  in_progress: { job_id: number; title: string }[]
  done: number
  failed: number
  total: number
  avg_seconds: number | null
  output_stats: Record<string, number>
  eta_seconds: number | null
  last_error: string | null
  jobs_total: number
  scored: number
  stale: number
  unscored: number
  failed_jobs: number
  model: string
  prompt_version: string
}

export interface ScoringHealth {
  reachable: boolean
  model: string
  model_present: boolean
  message: string
  models: string[]
  pull_command: string
}

export interface FullListingResult {
  ok: boolean
  message: string
  can_paste: boolean
  characters: number
}
