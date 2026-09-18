import type { ApiErrorResponse } from './types';

import axios, { type AxiosInstance, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios';

import { CONFIG } from 'src/global-config';

// ----------------------------------------------------------------------

export class ApiError extends Error {
  code: string;
  status: number;
  requestId: string;
  details?: unknown[];

  constructor(status: number, data: ApiErrorResponse) {
    super(data.message || 'An unexpected API error occurred');
    this.name = 'ApiError';
    this.status = status;
    this.code = data.code || 'unknown_error';
    this.requestId = data.request_id || '';
    this.details = data.details || [];
  }
}

// ----------------------------------------------------------------------

const rawBaseUrl = CONFIG.serverUrl || 'http://127.0.0.1:8000';
const normalizedBaseUrl = rawBaseUrl.endsWith('/') ? rawBaseUrl.slice(0, -1) : rawBaseUrl;
const API_BASE_URL = normalizedBaseUrl.endsWith('/api/v1')
  ? normalizedBaseUrl
  : `${normalizedBaseUrl}/api/v1`;

export const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
});

apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  // Attach idempotency key on write requests if not explicitly set
  if (['post', 'put', 'patch', 'delete'].includes(config.method?.toLowerCase() || '')) {
    if (!config.headers['Idempotency-Key']) {
      config.headers['Idempotency-Key'] = `idem-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
    }
  }
  return config;
});

apiClient.interceptors.response.use(
  (response: AxiosResponse) => response,
  (error) => {
    if (error.response) {
      const status = error.response.status;
      const data = (error.response.data || {}) as ApiErrorResponse;
      return Promise.reject(new ApiError(status, data));
    }
    return Promise.reject(
      new ApiError(503, {
        code: 'network_error',
        message: error.message || 'Cannot reach backend service.',
        request_id: '',
      })
    );
  }
);
