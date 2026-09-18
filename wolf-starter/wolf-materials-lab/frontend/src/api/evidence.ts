import type { RecordLineageResponse, EvidenceDetailResponse } from './types';

import { apiClient } from './client';

// ----------------------------------------------------------------------

export async function getEvidenceDetail(evidenceId: string): Promise<EvidenceDetailResponse> {
  const response = await apiClient.get<EvidenceDetailResponse>(`/evidence/${evidenceId}`);
  return response.data;
}

export async function getRecommendationEvidence(
  recommendationId: string
): Promise<EvidenceDetailResponse[]> {
  const response = await apiClient.get<EvidenceDetailResponse[]>(
    `/recommendations/${recommendationId}/evidence`
  );
  return response.data;
}

export async function getRecordLineage(recordId: string): Promise<RecordLineageResponse> {
  const response = await apiClient.get<RecordLineageResponse>(`/records/${recordId}/lineage`);
  return response.data;
}
