import { ApiError } from 'src/api/client';

// ----------------------------------------------------------------------

export interface UserFacingError {
  title: string;
  message: string;
  actionHint?: string;
  isConflict: boolean;
  requestId?: string;
}

export function parseApiError(error: unknown): UserFacingError {
  if (error instanceof ApiError) {
    if (error.status === 409 || error.code === 'conflict') {
      return {
        title: 'Version Conflict Detected',
        message:
          'The recommendation or record has been updated since you loaded it. Please refresh to inspect the latest version before submitting.',
        actionHint: 'Refresh and compare current version',
        isConflict: true,
        requestId: error.requestId,
      };
    }

    if (error.status === 400 || error.code === 'invalid_request') {
      return {
        title: 'Invalid Request',
        message: error.message || 'One or more submitted values are invalid.',
        actionHint: 'Check submitted fields and try again',
        isConflict: false,
        requestId: error.requestId,
      };
    }

    if (error.status === 404 || error.code === 'not_found') {
      return {
        title: 'Resource Not Found',
        message: error.message || 'The requested source, workflow, or recommendation was not found.',
        actionHint: 'Verify the identifier or start a new workflow',
        isConflict: false,
        requestId: error.requestId,
      };
    }

    if (error.status === 503 || error.code === 'dependency_unavailable') {
      return {
        title: 'Service Temporarily Unavailable',
        message: 'The calculation service or backend store is temporarily busy.',
        actionHint: 'Wait a moment and try again',
        isConflict: false,
        requestId: error.requestId,
      };
    }

    return {
      title: 'Request Failed',
      message: error.message || 'An internal backend error occurred.',
      actionHint: error.requestId ? `Reference Request ID: ${error.requestId}` : 'Please try again',
      isConflict: false,
      requestId: error.requestId,
    };
  }

  if (error instanceof Error) {
    return {
      title: 'Unexpected Error',
      message: error.message,
      isConflict: false,
    };
  }

  return {
    title: 'Unknown Error',
    message: 'An unexpected error occurred while communicating with the server.',
    isConflict: false,
  };
}
