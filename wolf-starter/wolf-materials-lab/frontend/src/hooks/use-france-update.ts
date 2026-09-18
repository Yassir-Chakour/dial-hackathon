import type {
  ExceptionItem,
  ReviewQueueItem,
  RecommendationDetail,
  RecommendationSummary,
  EvidenceDetailResponse,
  SubmitCorrectionRequest,
  RecommendationHistoryItem,
  RecommendationChangesResponse,
} from 'src/api/types';

import { useState, useEffect, useCallback } from 'react';

import { parseApiError } from 'src/lib/api-errors';
import { getRecommendationEvidence } from 'src/api/evidence';
import { uploadSourceFile, getFranceDemoFixture } from 'src/api/sources';
import {
  replayEvent,
  listExceptions,
  revokeApproval,
  listReviewQueue,
  submitCorrection,
  resolveReviewItem,
} from 'src/api/reviews';
import {
  getRecommendation,
  listRecommendations,
  rejectRecommendation,
  approveRecommendation,
  getRecommendationChanges,
  getRecommendationHistory,
} from 'src/api/recommendations';

import { useWorkflowStatus } from './use-workflow-status';

// ----------------------------------------------------------------------

export interface FeedbackState {
  type: 'success' | 'error' | 'warning' | 'info';
  title: string;
  message: string;
  isConflict?: boolean;
}

export function useFranceUpdate() {
  const [recommendations, setRecommendations] = useState<RecommendationSummary[]>([]);
  const [activeRecommendation, setActiveRecommendation] = useState<RecommendationDetail | null>(null);
  const [changes, setChanges] = useState<RecommendationChangesResponse | null>(null);
  const [history, setHistory] = useState<RecommendationHistoryItem[]>([]);
  const [evidenceList, setEvidenceList] = useState<EvidenceDetailResponse[]>([]);
  const [reviewQueue, setReviewQueue] = useState<ReviewQueueItem[]>([]);
  const [exceptions, setExceptions] = useState<ExceptionItem[]>([]);

  const [loading, setLoading] = useState<boolean>(true);
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [feedback, setFeedback] = useState<FeedbackState | null>(null);

  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const { runData, isPolling, refresh: refreshRun } = useWorkflowStatus(selectedRunId);

  // Fetch all initial or updated France data
  const loadFranceData = useCallback(async () => {
    setLoading(true);
    try {
      // 1. Fetch recommendations for market FR
      const recs = await listRecommendations({ market: 'FR', limit: 10 });
      setRecommendations(recs);

      // Select latest recommendation if available
      const latestSummary = recs[0];
      if (latestSummary) {
        const [recDetail, recChanges, recHistory, recEvidence] = await Promise.all([
          getRecommendation(latestSummary.id),
          getRecommendationChanges(latestSummary.id),
          getRecommendationHistory(latestSummary.id),
          getRecommendationEvidence(latestSummary.id).catch(() => []),
        ]);

        setActiveRecommendation(recDetail);
        setChanges(recChanges);
        setHistory(recHistory);
        setEvidenceList(recEvidence);
      } else {
        setActiveRecommendation(null);
        setChanges(null);
        setHistory([]);
        setEvidenceList([]);
      }

      // 2. Fetch Review Queue and Exceptions
      const [queue, excs] = await Promise.all([
        listReviewQueue(),
        listExceptions({ limit: 20 }),
      ]);
      setReviewQueue(queue);
      setExceptions(excs);

      // If there is an active paused run in review queue, focus it
      if (queue.length > 0 && !selectedRunId) {
        setSelectedRunId(queue[0].run_id);
      }
    } catch (err) {
      const parsed = parseApiError(err);
      setFeedback({
        type: 'error',
        title: parsed.title,
        message: parsed.message,
      });
    } finally {
      setLoading(false);
    }
  }, [selectedRunId]);

  useEffect(() => {
    loadFranceData();
  }, [loadFranceData]);

  // If a workflow completes or resumes, refresh recommendations
  useEffect(() => {
    if (runData?.status === 'completed' || runData?.status === 'paused') {
      loadFranceData();
    }
  }, [runData?.status, loadFranceData]);

  // Action: Upload the official synthetic France v2 fixture & start workflow
  const startDemoWorkflow = async (csvContent?: string) => {
    setActionLoading(true);
    setFeedback(null);
    try {
      const sourceContent = csvContent || (await getFranceDemoFixture());

      const uploadRes = await uploadSourceFile(
        sourceContent,
        'FR-v2--Sheet1.csv',
        'FR',
        true
      );

      if (uploadRes.workflow_run_id) {
        setSelectedRunId(uploadRes.workflow_run_id);
        setFeedback({
          type: 'info',
          title: 'France Source Received',
          message: `Uploaded synthetic France file. Workflow run ${uploadRes.workflow_run_id} initiated.`,
        });
      } else {
        setFeedback({
          type: 'success',
          title: 'Source Ingested',
          message: `Source file ${uploadRes.source_id} received. Ready to process.`,
        });
      }
      await loadFranceData();
    } catch (err) {
      const parsed = parseApiError(err);
      setFeedback({
        type: 'error',
        title: parsed.title,
        message: parsed.message,
      });
    } finally {
      setActionLoading(false);
    }
  };

  // Action: Resume paused workflow run (resolve review item)
  const handleResumeWorkflow = async (action: string, correctionPayload?: Record<string, unknown>) => {
    if (!selectedRunId) return;
    setActionLoading(true);
    setFeedback(null);
    try {
      await resolveReviewItem(selectedRunId, action, correctionPayload);
      setFeedback({
        type: 'success',
        title: 'Review Resolved',
        message: `Action '${action}' applied to run. Execution resumed.`,
      });
      refreshRun();
      await loadFranceData();
    } catch (err) {
      const parsed = parseApiError(err);
      setFeedback({
        type: 'error',
        title: parsed.title,
        message: parsed.message,
        isConflict: parsed.isConflict,
      });
    } finally {
      setActionLoading(false);
    }
  };

  // Action: Submit reviewer correction
  const handleSubmitCorrection = async (payload: SubmitCorrectionRequest) => {
    if (!activeRecommendation) return;
    setActionLoading(true);
    setFeedback(null);
    try {
      const res = await submitCorrection(activeRecommendation.id, payload);
      setFeedback({
        type: 'success',
        title: 'Correction Submitted',
        message: `Correction recorded for field '${res.field_name}'. Recommendation updated to needs_review.`,
      });
      await loadFranceData();
    } catch (err) {
      const parsed = parseApiError(err);
      setFeedback({
        type: 'error',
        title: parsed.title,
        message: parsed.message,
        isConflict: parsed.isConflict,
      });
    } finally {
      setActionLoading(false);
    }
  };

  // Action: Approve current recommendation version
  const handleApprove = async (reason = 'Approved by reviewer after inspecting evidence') => {
    if (!activeRecommendation) return;
    setActionLoading(true);
    setFeedback(null);
    try {
      const res = await approveRecommendation(
        activeRecommendation.id,
        activeRecommendation.calculation_hash,
        reason
      );
      setFeedback({
        type: 'success',
        title: 'Recommendation Approved',
        message: `Approval ID ${res.approval_id} committed with verified calculation hash ${res.calculation_hash.slice(0, 8)}…`,
      });
      await loadFranceData();
    } catch (err) {
      const parsed = parseApiError(err);
      setFeedback({
        type: parsed.isConflict ? 'warning' : 'error',
        title: parsed.title,
        message: parsed.message,
        isConflict: parsed.isConflict,
      });
      if (parsed.isConflict) {
        // Automatically refresh on conflict to show updated version
        await loadFranceData();
      }
    } finally {
      setActionLoading(false);
    }
  };

  // Action: Reject recommendation
  const handleReject = async (reason: string) => {
    if (!activeRecommendation) return;
    setActionLoading(true);
    setFeedback(null);
    try {
      await rejectRecommendation(
        activeRecommendation.id,
        reason,
        activeRecommendation.calculation_hash
      );
      setFeedback({
        type: 'info',
        title: 'Recommendation Rejected',
        message: `Recommendation version marked as rejected. Audit history preserved.`,
      });
      await loadFranceData();
    } catch (err) {
      const parsed = parseApiError(err);
      setFeedback({
        type: 'error',
        title: parsed.title,
        message: parsed.message,
      });
    } finally {
      setActionLoading(false);
    }
  };

  // Action: Revoke existing approval
  const handleRevoke = async (approvalId: string, reason: string) => {
    setActionLoading(true);
    setFeedback(null);
    try {
      await revokeApproval(approvalId, reason);
      setFeedback({
        type: 'warning',
        title: 'Approval Revoked',
        message: 'Active approval revoked. Recommendation reverted to review status.',
      });
      await loadFranceData();
    } catch (err) {
      const parsed = parseApiError(err);
      setFeedback({
        type: 'error',
        title: parsed.title,
        message: parsed.message,
      });
    } finally {
      setActionLoading(false);
    }
  };

  // Action: Replay event safely
  const handleReplay = async (eventId: string, mode: 'dry_run' | 'apply_if_safe' = 'dry_run') => {
    setActionLoading(true);
    setFeedback(null);
    try {
      const res = await replayEvent(eventId, mode);
      setFeedback({
        type: 'info',
        title: 'Event Replay Verified',
        message: `Mode: ${res.mode}. Identical result confirmed (Hash: ${res.replay_result_hash.slice(0, 8)}…). No duplicate counts.`,
      });
    } catch (err) {
      const parsed = parseApiError(err);
      setFeedback({
        type: 'error',
        title: parsed.title,
        message: parsed.message,
      });
    } finally {
      setActionLoading(false);
    }
  };

  return {
    recommendations,
    activeRecommendation,
    changes,
    history,
    evidenceList,
    reviewQueue,
    exceptions,
    selectedRunId,
    setSelectedRunId,
    runData,
    isPolling,
    loading,
    actionLoading,
    feedback,
    setFeedback,
    loadFranceData,
    startDemoWorkflow,
    handleResumeWorkflow,
    handleSubmitCorrection,
    handleApprove,
    handleReject,
    handleRevoke,
    handleReplay,
  };
}
