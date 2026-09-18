import type { WorkflowRunDetailResponse } from 'src/api/types';

import { useRef, useState, useEffect, useCallback } from 'react';

import { getWorkflowRun } from 'src/api/workflows';

// ----------------------------------------------------------------------

interface UseWorkflowStatusOptions {
  pollingIntervalMs?: number;
  maxIterations?: number;
}

export function useWorkflowStatus(
  initialRunId: string | null,
  options: UseWorkflowStatusOptions = {}
) {
  const { pollingIntervalMs = 1500, maxIterations = 30 } = options;

  const [runId, setRunId] = useState<string | null>(initialRunId);
  const [runData, setRunData] = useState<WorkflowRunDetailResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<Error | null>(null);
  const [isPolling, setIsPolling] = useState<boolean>(false);

  const iterationsRef = useRef<number>(0);
  const isMountedRef = useRef<boolean>(true);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  // The workflow run is created after the user uploads a source. Keep the
  // polling hook synchronized with that newly-created run instead of only
  // reading the initial value from the first render.
  useEffect(() => {
    setRunId(initialRunId);
  }, [initialRunId]);

  const fetchRun = useCallback(async (id: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await getWorkflowRun(id);
      if (isMountedRef.current) {
        setRunData(data);
      }
      return data;
    } catch (err) {
      if (isMountedRef.current) {
        setError(err instanceof Error ? err : new Error('Failed to fetch workflow run'));
      }
      return null;
    } finally {
      if (isMountedRef.current) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    if (!runId) {
      setRunData(null);
      setIsPolling(false);
      return () => {};
    }

    let timeoutId: NodeJS.Timeout | null = null;
    iterationsRef.current = 0;

    const poll = async () => {
      if (!isMountedRef.current) return;
      iterationsRef.current += 1;

      const data = await fetchRun(runId);
      if (!data || !isMountedRef.current) {
        setIsPolling(false);
        return;
      }

      // Stop condition: status is terminal or paused
      if (['paused', 'needs_review', 'completed', 'failed'].includes(data.status)) {
        setIsPolling(false);
        return;
      }

      if (iterationsRef.current >= maxIterations) {
        setIsPolling(false);
        return;
      }

      setIsPolling(true);
      timeoutId = setTimeout(poll, pollingIntervalMs);
    };

    poll();

    return () => {
      if (timeoutId) clearTimeout(timeoutId);
    };
  }, [runId, fetchRun, pollingIntervalMs, maxIterations]);

  const refresh = useCallback(() => {
    if (runId) {
      fetchRun(runId);
    }
  }, [runId, fetchRun]);

  return {
    runId,
    setRunId,
    runData,
    loading,
    error,
    isPolling,
    refresh,
  };
}
