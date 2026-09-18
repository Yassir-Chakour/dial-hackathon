import type {
  SourceVersionItem,
  SourceDetailResponse,
  SourceUploadResponse,
} from './types';

import { apiClient } from './client';

// ----------------------------------------------------------------------

export async function uploadSourceFile(
  fileBytes: Blob | string,
  filename: string,
  market = 'FR',
  autoProcess = false
): Promise<SourceUploadResponse> {
  const headers: Record<string, string> = {
    'Content-Type': 'text/csv',
    'X-Filename': filename,
    'X-Market': market,
  };

  const response = await apiClient.post<SourceUploadResponse>('/sources', fileBytes, {
    headers,
    params: { auto_process: autoProcess },
  });
  return response.data;
}

export async function getSourceDetail(sourceId: string): Promise<SourceDetailResponse> {
  const response = await apiClient.get<SourceDetailResponse>(`/sources/${sourceId}`);
  return response.data;
}

export async function getSourceVersions(sourceId: string): Promise<SourceVersionItem[]> {
  const response = await apiClient.get<SourceVersionItem[]>(`/sources/${sourceId}/versions`);
  return response.data;
}

export async function processSourceVersion(
  versionId: string,
  idempotencyKey?: string
): Promise<{ source_version_id: string; status: string; market: string; message: string }> {
  const response = await apiClient.post<{
    source_version_id: string;
    status: string;
    market: string;
    message: string;
  }>(`/source-versions/${versionId}/process`, { idempotency_key: idempotencyKey });
  return response.data;
}
