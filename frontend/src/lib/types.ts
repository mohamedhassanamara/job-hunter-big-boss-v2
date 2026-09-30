// Mirrors backend/app/schemas — keep in sync. JSON is snake_case end to end.

export type Stage = 'new' | 'shortlisted' | 'cv_ready' | 'ready' | 'done' | 'interview' | 'closed'
export type Route = 'undecided' | 'cold_email' | 'web_apply'

/** Both routes of a job (services/tracks.py): the web application and the cold email. */
export type ApplicationTrack = 'not_ready' | 'ready' | 'applied'
export type OutreachTrack = 'no_contact' | 'contact' | 'drafted' | 'approved' | 'queued' | 'sent'
export interface Tracks {
  application: ApplicationTrack
  outreach: OutreachTrack
  applied_at: string | null
  web_method: ApplyMethod | null
  contact_name: string | null
  draft_id: number | null
  sent_at: string | null
}
export type ContactTier = 'apollo_dump' | 'lookup_queued' | 'lookup_found' | 'none'
export type Source = 'adzuna' | 'remotive' | 'arbeitnow' | 'wttj' | 'boards' | 'bayt'

export interface CompanyBoard {
  ats: 'greenhouse' | 'lever' | 'ashby' | 'workable' | 'smartrecruiters'
  token: string
  company: string
}
export type RemoteType = 'remote' | 'hybrid' | 'onsite' | 'unknown'
export type FitBand = 'strong' | 'good' | 'fair' | 'weak' | 'failed' | 'pending'
export type CloseReason =
  | 'dismissed'
  | 'rejected'
  | 'withdrawn'
  | 'no_response'
  | 'offer_accepted'
  | 'offer_declined'
  | 'offer' // legacy, shown as "Offer"
export type ApplyMethod = 'company_site' | 'job_board' | 'email' | 'other'
export type ResponseKind = 'positive' | 'rejection' | 'other'
export type InterviewType = 'hr' | 'technical' | 'take_home' | 'final' | 'other'
export type InterviewOutcome = 'pending' | 'passed' | 'failed' | 'cancelled'
export type ExperienceKind = 'job' | 'project' | 'skill' | 'education' | 'certification' | 'volunteering' | 'summary'

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
  /** Provenance: which model and prompt version produced this score. */
  model: string | null
  prompt_version: string | null
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
  tracks: Tracks
  contact_tier: ContactTier
  close_reason: CloseReason | null
  stage_changed_at: string
}

export interface JobListItem {
  id: number
  description_level: DescriptionLevel
  user_label: UserLabel | null
  matched_track: string | null
  matched_role: string | null
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
  role_rank: number // position in Settings → Contacts ranking (999 = unranked)
  role_label: string | null
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
  locked: boolean // sent with the application: never changes
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
  tracking: TrackedApplication | null // set once applied
  lookup_status: LookupStatus | null // the company's Apollo lookup
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
  tracks: Tracks
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

export interface CVRole {
  item_id: number | null
  title: string
  org: string
  location: string
  start: string
  end: string
  bullets: string[]
}

export interface CVDocument {
  summary: string
  skills: { category: string; items: string[] }[]
  roles: CVRole[]
  projects: { item_id: number | null; name: string; stack: string[]; label: string; bullets: string[] }[]
  certifications: { item_id: number | null; name: string; issuer: string; credential_id: string; url: string }[]
  education: { item_id: number | null; school: string; degree: string; location: string; start: string; end: string }[]
  volunteering: CVRole[]
}

export interface CVViolation {
  type: string
  severity: 'error' | 'warning'
  message: string
  where: string
}

export interface CVVersion {
  id: number
  application_id: number
  version: number
  status: CVStatus
  content: CVDocument
  page_count: number | null
  fill: number | null
  fit_passes: number
  template: string
  generator_model: string
  violations: CVViolation[]
  duration_ms: number | null
  error: string | null
  has_pdf: boolean
  created_at: string
  updated_at: string
}

export interface CVUsageBullet {
  key: string
  text: string
  source: string
  priority: number
  shown: boolean
}

export interface CVUsageEntry {
  key: string
  item_id: number
  title: string
  org: string | null
  relevance: number
  shown: boolean
  bullets: CVUsageBullet[]
}

export interface CVSummaryCitation {
  id: number
  title: string
  kind: string
}

export interface CVUsage {
  summary: {
    text: string
    full: string
    short: string
    edited: boolean
    sentences: { text: string; citations: CVSummaryCitation[] }[]
    grounding: { attempts: number; fallback: string | null; rejected: { text: string; reasons: string[] }[][] } | null
  }
  roles: CVUsageEntry[]
  projects: CVUsageEntry[]
  certifications: { key: string; item_id: number; title: string; org: string | null; shown: boolean }[]
  force_in: string[]
  force_out: string[]
}

export interface ReadinessItem {
  key: string
  severity: 'blocker' | 'warning'
  message: string
}

export interface CVTemplateInfo {
  name: string
  description: string
  paper: string
  builtin: boolean
  valid: boolean
  pages: number | null
  error: string | null
  is_default: boolean
}

export interface CVStudio {
  application_id: number
  job_id: number
  job_title: string
  company_name: string
  matched_track: string | null
  stage: Stage
  route: Route
  has_contact: boolean
  versions: CVVersion[]
  readiness: ReadinessItem[]
  templates: CVTemplateInfo[]
  usage: CVUsage | null
  download_name: string | null
}

export interface CVPatchInput {
  force_in?: string[]
  force_out?: string[]
  text?: Record<string, string>
  template?: string
}

export interface CVApproveResult {
  version: CVVersion
  stage: Stage
  route: Route
  next_step: 'draft_email' | 'apply'
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
  contact: { id: number; full_name: string; title: string | null; email: string | null; role_label: string | null } | null
  subject: string
  body: string // your text (greeting, sentences, ask); signature and opt-out are added when sent
  status: DraftStatus
  edited: boolean
  model: string
  cv_version: number | null
  created_at: string
  updated_at: string
  cv_version_id: number | null
  sentences: { text: string; citations: number[]; about_job: boolean }[]
  citations: Record<string, string> // pool id -> "Role · Org"
  violations: Violation[]
  attempts: number
  prompt_version: string | null
  duration_ms: number | null
  full_body: string // exactly as sent
  test_sent_at: string | null
  sent_at: string | null
  generated_via: string // "claude -p" = Claude Code headless on your subscription
  auth: string | null // the CLI's apiKeySource ("none" = subscription)
  application_mention: string | null // "I have also applied through your careers page on …"
  mention_included: boolean
}

export interface DraftReviewItem {
  draft_id: number
  job_id: number
  job_title: string
  company_name: string
  contact_name: string | null
  created_at: string
}

export type OutreachStepName = 'contact' | 'cv' | 'draft' | 'review' | 'queue' | 'queued' | 'sent'

export interface WhoToContact {
  company_size: string
  small: boolean
  reason: string
  roles: { label: string; titles: string[] }[]
  linkedin_query: string
  linkedin_url: string
  apollo: { company: string; domain: string; titles: string[]; seniority: string[] }
}

export interface OutreachStep {
  step: OutreachStepName
  route: Route
  contact_tier: ContactTier
  lookup_status: LookupStatus | null
  has_contact: boolean
  has_email: boolean
  cv_version: number | null
  draft: Draft | null
  queue_position: number | null
  queue_eta: string | null
  queue_status: QueueStatus
  sent_at: string | null
  who_to_contact: WhoToContact | null
}

export interface Violation {
  type: string
  severity: 'error' | 'warning'
  message: string
  where: string
}

export interface SendLogEntry {
  id: number
  draft_id: number | null
  kind: 'test' | 'real'
  to: string
  subject: string
  status: 'sent' | 'failed'
  error: string | null
  message_id: string | null
  attachment: string | null
  at: string
}

export type QueueStatus = 'idle' | 'running' | 'paused'

export interface QueueItem {
  id: number
  position: number
  status: 'pending' | 'sending' | 'sent' | 'failed' | 'cancelled' | 'unknown'
  attempts: number
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
  counts: { pending: number; sent: number; failed: number; unknown: number }
  items: QueueItem[]
  test_sent: boolean // a test email reached you: required before starting
  own_address: string
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
  url?: string | null
  credential_id?: string | null
}

export interface ExperienceItem extends ExperienceInput {
  id: number
  position: number
  is_placeholder: boolean
  updated_at: string
}

// Contacts
export type LookupStatus = 'queued' | 'found' | 'not_found' | 'skipped' | 'never'
export type CompanyFilter = 'with_jobs' | 'has_contacts' | 'needs_lookup' | 'no_contact' | 'all'

export interface CompanyListItem {
  id: number
  name: string
  domain: string | null
  contact_count: number
  open_jobs: number
  contacted_at: string | null
  lookup_status: LookupStatus | null
  best_contact: string | null
  employees: number | null
  employees_max: number | null // "under N"
  size_source: 'manual' | 'apollo_list' | null
  size_label: string
  small: boolean // uses the small-company contact order
}

export interface CompanyList {
  items: CompanyListItem[]
  total: number
}

export interface CompanyJob {
  application_id: number
  job_id: number
  title: string
  stage: Stage
  stage_label: string
  route: Route
  contact_tier: ContactTier
  contact_id: number | null
  fit: FitBrief | null
}

export interface CompanyDetail extends CompanyListItem {
  website: string | null
  contacts: Contact[] // most relevant role first
  jobs: CompanyJob[]
}

export interface FilePreview {
  filename: string
  sha256: string
  total_rows: number
  columns: string[]
  mapping: Record<string, string | null>
  sample: Record<string, string>[]
  already_imported_at: string | null
}

export interface ImportRun {
  id: number
  filename: string
  status: 'running' | 'done' | 'failed'
  total: number
  processed: number
  created: number
  updated: number
  skipped: number
  skipped_reasons: Record<string, number>
  companies_created: number
  error: string | null
  started_at: string
  finished_at: string | null
  backup_path: string | null
}

export interface LookupItem {
  company_id: number
  company_name: string
  domain: string | null
  status: LookupStatus
  priority: number
  open_jobs: number
  best_job_id: number | null
  best_job_title: string | null
  best_fit: number | null
  queued_at: string
  shortlisted: number
  newest_at: string | null
  reason: string // why it's at this position
  aggregator: string[] // "looks like a job board" signals (you confirm)
}

export interface LookupQueue {
  daily_cap: number
  used_today: number
  total: number
  items: LookupItem[]
}

export interface NewContact {
  full_name: string
  title?: string | null
  email?: string | null
  linkedin_url?: string | null
  notes?: string
}

export interface MatchGroup {
  group: string
  jobs: number
  with_contact: number
  queued: number
  no_contact: number
}

export interface MatchReport {
  totals: { jobs: number; with_contact: number; queued: number; no_contact: number }
  by_track: MatchGroup[]
  by_country: MatchGroup[]
  lookup_queue: number
  contacts: number
  companies_with_contacts: number
  changed: number | null
  at: string
}

export interface MergeSide {
  id: number
  name: string
  jobs: number
  contacts: number
}

export interface MergeSuggestion {
  a: MergeSide
  b: MergeSide
  reason: string
}

export interface RoleGroup {
  label: string
  keywords: string[]
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

export type VariantLang = 'en' | 'fr' | 'es' | 'de' | 'it' | 'nl'

export interface TrackRole {
  title: string
  /** Per-language equivalents. null = not set yet: the server suggests them on save. */
  variants: Partial<Record<VariantLang, string[]>> | null
}

export interface Track {
  name: string
  years_experience: number | null
  roles: TrackRole[]
}

export interface SearchProfile {
  name: string
  /** All role titles, derived from `tracks` on save (read-only). */
  roles: string[]
  tracks: Track[]
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
  drafts_to_approve: DraftReviewItem[]
  emails_to_queue: DraftReviewItem[] // approved, not yet in the send queue
  ready_to_apply: PipelineCard[]
  also_email: PipelineCard[] // applied on the website, nobody emailed yet
  reminders: Reminder[]
  upcoming_interviews: UpcomingInterview[] // next 14 days, pending
  stats_summary: StatsSummary
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
  ready_to_apply: number
}

export interface SearchHit {
  kind: 'job' | 'company' | 'contact'
  id: number
  title: string
  subtitle: string
  href: string
}

export interface ScoringRunInfo {
  id: number
  trigger: string
  /** Model in use now (the fallback after a cloud usage limit). */
  model: string
  primary_model: string
  fallback_model: string | null
  /** Set when a usage limit switched the run to the local model. */
  fallback_reason: string | null
  fallback_at: string | null
  retried_429: number
  quota_hits: number
  concurrency_limit: number | null
  concurrency_min: number | null
  concurrency_max: number | null
  finished: boolean
}

export interface RescorePreview {
  scope: string
  count: number
  model: string
  eta_seconds: number | null
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
  run: ScoringRunInfo | null
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

// ---- Tracking (after the CV) -------------------------------------------------------------

export interface ReadyItem {
  application_id: number
  job_id: number
  title: string
  company: string
  track: string | null
  country: string | null
  url: string
  cv_version_id: number
  cv_version: number
  stage: Stage
  letter_id: number | null
  letter_version: number | null
  letter_status: 'none' | 'draft' | 'approved'
}

export interface ApplicationResponse {
  id: number
  kind: ResponseKind
  received_at: string
  notes: string
}

export interface Interview {
  id: number
  round: number
  scheduled_at: string
  type: InterviewType
  notes: string
  outcome: InterviewOutcome
}

export interface TrackedApplication {
  application_id: number
  job_id: number
  title: string
  company: string
  track: string | null
  country: string | null
  source: Source
  url: string
  stage: Stage
  stage_label: string
  close_reason: CloseReason | null
  applied_at: string
  applied_method: ApplyMethod | null
  applied_cv_version_id: number | null
  applied_cv_version: number | null
  applied_cover_letter_id: number | null
  applied_cover_letter_version: number | null
  applied_notes: string
  responses: ApplicationResponse[]
  interviews: Interview[]
  days_to_first_response: number | null
}

export interface Reminder {
  application_id: number
  job_id: number
  job_title: string
  company: string
  key: string // followup:7 · followup:14 · ghost
  kind: 'followup' | 'ghost'
  days: number
  due_at: string
  applied_at: string
}

export interface UpcomingInterview {
  interview_id: number
  application_id: number
  job_id: number
  job_title: string
  company_name: string
  round: number
  type: InterviewType
  scheduled_at: string
}

export interface StatsSummary {
  applied_this_week: number
  applied_total: number
  responded: number
  response_rate: number | null
}

export interface Rate {
  count: number
  total: number
  rate: number | null
}

export interface StatsGroup {
  group: string
  applied: number
  response: Rate
  interview: Rate
}

export interface Stats {
  applied: number
  per_week: { week: string; count: number }[]
  response: Rate
  interview: Rate
  median_days_to_first_response: number | null
  by_track: StatsGroup[]
  by_country: StatsGroup[]
  by_source: StatsGroup[]
  both_routes: number
  by_route: StatsGroup[] // web / email / both
}

export interface TrackingFilters {
  track?: string[]
  country?: string[]
  source?: string[]
  stage?: string[]
  start?: string
  end?: string
}

// ---- Cover letters (mirror app/schemas/letters.py) -----------------------------------------

export type LetterLanguage = 'fr' | 'en'
export type LetterFormat = 'pdf' | 'form'

export interface LetterSentence {
  text: string
  citations: number[]
  about_job: boolean
}

export interface LetterParagraph {
  text: string
  edited: boolean
  sentences: LetterSentence[]
}

export interface CoverLetter {
  id: number
  application_id: number
  version: number
  status: CVStatus
  language: LetterLanguage
  format: LetterFormat
  question: string | null
  char_limit: number | null
  salutation: string
  paragraphs: LetterParagraph[]
  ask: string
  closing: string
  text: string
  word_count: number
  page_count: number | null
  has_pdf: boolean
  violations: Violation[]
  sources: Record<string, string>
  cv_version_id: number | null
  cv_version: number | null
  generator_model: string
  duration_ms: number | null
  error: string | null
  locked_at: string | null
  download_name: string
  created_at: string
  updated_at: string
}

export interface LetterStudio {
  application_id: number
  job_id: number
  job_title: string
  company_name: string
  stage: Stage
  route: Route
  language_setting: 'auto' | LetterLanguage
  detected_language: LetterLanguage
  language: LetterLanguage
  approved_cv_id: number | null
  approved_cv_version: number | null
  template_ok: boolean
  letters: CoverLetter[]
}

export interface LetterPatchInput {
  salutation?: string
  paragraphs?: string[]
  ask?: string
}

export interface ApplicationAnswer {
  id: number
  application_id: number
  question: string
  char_limit: number | null
  answer: string
  length: number
  language: LetterLanguage
  edited: boolean
  sentences: LetterSentence[]
  sources: Record<string, string>
  violations: Violation[]
  created_at: string
  updated_at: string
}
