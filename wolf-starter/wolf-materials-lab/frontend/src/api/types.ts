/**
 * Phase Eight typed API contracts mirroring the Phase Seven backend schemas.
 */

export interface PageInfo {
  next_cursor?: string | null;
  limit: number;
  total?: number | null;
}

export interface ApiErrorDetail {
  loc: (string | number)[];
  msg: string;
  type: string;
}

export interface ApiErrorResponse {
  code: string;
  message: string;
  request_id: string;
  details?: ApiErrorDetail[];
}

// --- Source Interfaces ---

export interface SourceUploadResponse {
  source_id: string;
  sha256: string;
  size_bytes: number;
  media_type: string;
  received_at: string;
  synthetic: boolean;
  workflow_run_id?: string | null;
}

export interface SourceDetailResponse {
  id: string;
  original_filename: string;
  media_type: string;
  size_bytes: number;
  sha256: string;
  received_at: string;
  version_count: number;
}

export interface SourceVersionItem {
  id: string;
  version_label: string;
  market: string;
  status: string;
  update_mode: string;
  parent_version_id?: string | null;
  created_at: string;
}

export interface ProcessVersionRequest {
  idempotency_key?: string | null;
}

// --- Workflow Interfaces ---

export interface WorkflowRunDetailResponse {
  run_id: string;
  event_id: string;
  market: string;
  stage: string;
  status: string;
  workflow_version: string;
  source_file_id?: string | null;
  source_version_id?: string | null;
  previous_version_id?: string | null;
  reconciliation_result_id?: string | null;
  recommendation_draft?: Record<string, unknown> | null;
  review_request?: {
    allowed_actions?: string[];
    blocking_issue_ids?: string[];
    checkpoint_id?: string;
    affected_record_ids?: string[];
    reason?: string;
    [key: string]: unknown;
  } | null;
  reconciliation?: RecommendationChangesResponse | null;
  issues: Record<string, unknown>[];
  history: string[];
}

export interface ResumeRunRequest {
  action: string;
  correction_payload?: Record<string, unknown> | null;
}

// --- Recommendation Interfaces ---

export interface RecommendationSummary {
  id: string;
  recommendation_key: string;
  source_version_id: string;
  status: string;
  calculation_hash: string;
  created_at: string;
  superseded_at?: string | null;
}

export interface RecommendationDetail {
  id: string;
  recommendation_key: string;
  source_version_id: string;
  status: string;
  facts: {
    amount?: string | number | null;
    category?: string;
    currency?: string | null;
    unit?: string | null;
    evidence_complete?: boolean;
    reasons?: string[];
    warnings?: string[];
    total_saving?: string | number;
    [key: string]: unknown;
  };
  explanation: {
    summary?: string;
    confidence_score?: number;
    uncertainties?: string[];
    assumptions?: string[];
    [key: string]: unknown;
  };
  calculation_hash: string;
  created_at: string;
  allowed_actions: string[];
}

export interface ChangeRecordItem {
  record_key?: string;
  product?: string;
  supplier?: string;
  old_value?: string | number | null;
  new_value?: string | number | null;
  currency?: string | null;
  unit?: string | null;
  lineage?: string;
  reason_code?: string;
  source_row_number?: number;
  source_record_id?: string;
  [key: string]: unknown;
}

export interface RecommendationChangesResponse {
  recommendation_id: string;
  scope: Record<string, unknown>;
  totals: {
    added_count?: number;
    replaced_count?: number;
    preserved_count?: number;
    removed_count?: number;
    total_spend_old?: string | number;
    total_spend_new?: string | number;
    spend_difference?: string | number;
    [key: string]: unknown;
  };
  added: ChangeRecordItem[];
  replaced: ChangeRecordItem[];
  removed_from_current: ChangeRecordItem[];
  preserved: ChangeRecordItem[];
}

export interface RecommendationHistoryItem {
  version_id: string;
  event_type: string;
  status: string;
  calculation_hash: string;
  timestamp: string;
  note?: string | null;
}

export interface ApproveRecommendationRequest {
  calculation_hash: string;
  reason?: string;
  idempotency_key?: string | null;
}

export interface RejectRecommendationRequest {
  reason: string;
  calculation_hash?: string | null;
}

export interface ApprovalResponse {
  approval_id: string;
  recommendation_id: string;
  decision: string;
  status: string;
  reviewer_id: string;
  calculation_hash: string;
  timestamp: string;
}

export interface RevokeApprovalRequest {
  reason: string;
}

// --- Correction Interfaces ---

export interface SubmitCorrectionRequest {
  source_record_id: string;
  field_name: string;
  original_value?: string | null;
  corrected_value: string;
  reason: string;
}

export interface CorrectionDetailResponse {
  id: string;
  source_record_id: string;
  field_name: string;
  original_value?: string | null;
  corrected_value: string;
  reviewer_id: string;
  reason: string;
  created_at: string;
}

// --- Evidence & Lineage Interfaces ---

export interface EvidenceDetailResponse {
  id: string;
  recommendation_id: string;
  source_record_id: string;
  source_file_id: string;
  relation: string;
  created_at: string;
}

export interface RecordLineageResponse {
  record_id: string;
  record_key: string;
  version_id: string;
  source_row_number: number;
  lineage: string;
  prior_record_id?: string | null;
}

// --- Replay Interfaces ---

export interface ReplayRequest {
  event_id: string;
  mode?: 'dry_run' | 'apply_if_safe';
}

export interface ReplayResponse {
  original_event_id: string;
  replayed: boolean;
  mode: string;
  identical_result: boolean;
  original_result_hash: string;
  replay_result_hash: string;
  status: string;
}

// --- Review Queue & Exceptions ---

export interface ReviewQueueItem {
  run_id: string;
  checkpoint_id: string;
  stage: string;
  status: string;
  blocking_issues: string[];
  allowed_actions: string[];
  created_at: string;
}

export interface ResolveReviewQueueRequest {
  action: string;
  correction?: Record<string, unknown> | null;
}

export interface ExceptionItem {
  id: string;
  event_id: string;
  code: string;
  severity: string;
  message: string;
  created_at: string;
}
