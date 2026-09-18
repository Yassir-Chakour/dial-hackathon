import type { WorkflowRunDetailResponse } from './types';

import { apiClient } from './client';

// ----------------------------------------------------------------------

export async function getWorkflowRun(runId: string): Promise<WorkflowRunDetailResponse> {
  const response = await apiClient.get<WorkflowRunDetailResponse>(`/workflow-runs/${runId}`);
  return response.data;
}

export async function resumeWorkflowRun(
  runId: string,
  action: string,
  correctionPayload?: Record<string, unknown> | null
): Promise<WorkflowRunDetailResponse> {
  const response = await apiClient.post<WorkflowRunDetailResponse>(`/workflow-runs/${runId}/resume`, {
    action,
    correction_payload: correctionPayload,
  });
  return response.data;
}

export async function cancelWorkflowRun(
  runId: string
): Promise<{ run_id: string; status: string; stage: string; message: string }> {
  const response = await apiClient.post<{
    run_id: string;
    status: string;
    stage: string;
    message: string;
  }>(`/workflow-runs/${runId}/cancel`);
  return response.data;
}
