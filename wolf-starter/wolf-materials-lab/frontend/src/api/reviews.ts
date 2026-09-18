import type {
  ExceptionItem,
  ReplayResponse,
  ReviewQueueItem,
  ApprovalResponse,
  SubmitCorrectionRequest,
  CorrectionDetailResponse,
} from './types';

import { apiClient } from './client';

// ----------------------------------------------------------------------

export async function submitCorrection(
  recommendationId: string,
  payload: SubmitCorrectionRequest
): Promise<CorrectionDetailResponse> {
  const response = await apiClient.post<CorrectionDetailResponse>(
    `/recommendations/${recommendationId}/corrections`,
    payload
  );
  return response.data;
}

export async function getCorrection(correctionId: string): Promise<CorrectionDetailResponse> {
  const response = await apiClient.get<CorrectionDetailResponse>(`/corrections/${correctionId}`);
  return response.data;
}

export async function revokeApproval(
  approvalId: string,
  reason: string
): Promise<ApprovalResponse> {
  const response = await apiClient.post<ApprovalResponse>(`/approvals/${approvalId}/revoke`, {
    reason,
  });
  return response.data;
}

export async function replayEvent(
  eventId: string,
  mode: 'dry_run' | 'apply_if_safe' = 'dry_run'
): Promise<ReplayResponse> {
  const response = await apiClient.post<ReplayResponse>('/replays', {
    event_id: eventId,
    mode,
  });
  return response.data;
}

export async function getReplay(replayId: string): Promise<ReplayResponse> {
  const response = await apiClient.get<ReplayResponse>(`/replays/${replayId}`);
  return response.data;
}

export async function listReviewQueue(): Promise<ReviewQueueItem[]> {
  const response = await apiClient.get<ReviewQueueItem[]>('/review-queue');
  return response.data;
}

export async function resolveReviewItem(
  runId: string,
  action: string,
  correction?: Record<string, unknown> | null
): Promise<{ run_id: string; status: string; stage: string; message: string }> {
  const response = await apiClient.post<{
    run_id: string;
    status: string;
    stage: string;
    message: string;
  }>(`/review-queue/${runId}/resolve`, {
    action,
    correction,
  });
  return response.data;
}

export async function listExceptions(params?: {
  severity?: string;
  code?: string;
  limit?: number;
}): Promise<ExceptionItem[]> {
  const response = await apiClient.get<ExceptionItem[]>('/exceptions', { params });
  return response.data;
}
