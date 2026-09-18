import type {
  ApprovalResponse,
  RecommendationDetail,
  RecommendationSummary,
  RecommendationHistoryItem,
  RecommendationChangesResponse,
} from './types';

import { apiClient } from './client';

// ----------------------------------------------------------------------

export async function listRecommendations(params?: {
  market?: string;
  status?: string;
  source_version_id?: string;
  limit?: number;
}): Promise<RecommendationSummary[]> {
  const response = await apiClient.get<RecommendationSummary[]>('/recommendations', { params });
  return response.data;
}

export async function getRecommendation(recommendationId: string): Promise<RecommendationDetail> {
  const response = await apiClient.get<RecommendationDetail>(`/recommendations/${recommendationId}`);
  return response.data;
}

export async function getRecommendationChanges(
  recommendationId: string
): Promise<RecommendationChangesResponse> {
  const response = await apiClient.get<RecommendationChangesResponse>(
    `/recommendations/${recommendationId}/changes`
  );
  return response.data;
}

export async function getRecommendationHistory(
  recommendationId: string
): Promise<RecommendationHistoryItem[]> {
  const response = await apiClient.get<RecommendationHistoryItem[]>(
    `/recommendations/${recommendationId}/history`
  );
  return response.data;
}

export async function approveRecommendation(
  recommendationId: string,
  calculationHash: string,
  reason = 'Approved by reviewer'
): Promise<ApprovalResponse> {
  const response = await apiClient.post<ApprovalResponse>(
    `/recommendations/${recommendationId}/approve`,
    {
      calculation_hash: calculationHash,
      reason,
    }
  );
  return response.data;
}

export async function rejectRecommendation(
  recommendationId: string,
  reason: string,
  calculationHash?: string
): Promise<ApprovalResponse> {
  const response = await apiClient.post<ApprovalResponse>(
    `/recommendations/${recommendationId}/reject`,
    {
      reason,
      calculation_hash: calculationHash,
    }
  );
  return response.data;
}
