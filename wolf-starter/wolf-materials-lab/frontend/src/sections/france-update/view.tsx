'use client';

import type { ChangeRecordItem } from 'src/api/types';

import { useState } from 'react';

import Box from '@mui/material/Box';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import AlertTitle from '@mui/material/AlertTitle';
import CircularProgress from '@mui/material/CircularProgress';

import { useFranceUpdate } from 'src/hooks/use-france-update';

import { DashboardContent } from 'src/layouts/dashboard';

import { ReviewQueue } from './review-queue';
import { UpdateHeader } from './update-header';
import { ApprovalPanel } from './approval-panel';
import { VersionCompare } from './version-compare';
import { EvidenceDrawer } from './evidence-drawer';
import { CorrectionForm } from './correction-form';
import { ChangeSetTable } from './change-set-table';
import { WorkflowTimeline } from './workflow-timeline';
import { RecommendationCard } from './recommendation-card';

// ----------------------------------------------------------------------

export function FranceUpdateView() {
  const {
    activeRecommendation,
    changes,
    history,
    reviewQueue,
    exceptions,
    selectedRunId,
    runData,
    isPolling,
    loading,
    actionLoading,
    feedback,
    loadFranceData,
    startDemoWorkflow,
    handleResumeWorkflow,
    handleSubmitCorrection,
    handleApprove,
    handleReject,
    handleReplay,
  } = useFranceUpdate();

  const [selectedEvidenceRecord, setSelectedEvidenceRecord] = useState<ChangeRecordItem | null>(null);
  const [evidenceDrawerOpen, setEvidenceDrawerOpen] = useState(false);

  const [correctionRecord, setCorrectionRecord] = useState<ChangeRecordItem | null>(null);
  const [correctionModalOpen, setCorrectionModalOpen] = useState(false);

  const handleOpenEvidence = (record: ChangeRecordItem) => {
    setSelectedEvidenceRecord(record);
    setEvidenceDrawerOpen(true);
  };

  const handleOpenCorrection = (record?: ChangeRecordItem) => {
    setCorrectionRecord(
      record ||
        (changes?.added?.[0] as ChangeRecordItem) || {
          record_key: 'TXN-000505',
          product: 'WLF-1001',
          supplier: 'sup-novex',
          new_value: '2475.64',
        }
    );
    setCorrectionModalOpen(true);
  };

  const handleReplayClick = () => {
    if (runData?.event_id) {
      handleReplay(runData.event_id, 'dry_run');
    } else {
      handleReplay('evt:wf:v2', 'dry_run');
    }
  };

  return (
    <DashboardContent>
      {/* Action and feedback notifications */}
      {feedback && (
        <Alert
          severity={feedback.type}
          sx={{ mb: 3 }}
          action={
            feedback.isConflict ? (
              <Button color="inherit" size="small" onClick={loadFranceData}>
                Refresh Version
              </Button>
            ) : undefined
          }
        >
          <AlertTitle>{feedback.title}</AlertTitle>
          {feedback.message}
        </Alert>
      )}

      {/* Header */}
      <UpdateHeader
        market="FR"
        updateMode="replacement"
        status={runData?.status || activeRecommendation?.status || 'ready'}
        isPolling={isPolling}
        actionLoading={actionLoading}
        onStartDemo={() => startDemoWorkflow()}
        onRefresh={loadFranceData}
        onReplay={handleReplayClick}
      />

      {loading && !activeRecommendation ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
          <CircularProgress />
        </Box>
      ) : (
        <>
          {/* Agent Workflow Execution Timeline */}
          <WorkflowTimeline
            currentStage={runData?.stage || 'intake'}
            status={runData?.status || 'idle'}
            runId={selectedRunId}
            history={runData?.history}
          />

          {/* Three-Way Comparison: Previous (v1), Incoming (v2), Reconciled */}
          <VersionCompare
            changes={changes}
            previousVersionId={runData?.previous_version_id}
            incomingVersionId={runData?.source_version_id}
          />

          {/* Reconciled Line Changes Table */}
          <ChangeSetTable
            changes={changes}
            onSelectEvidence={handleOpenEvidence}
            onOpenCorrection={handleOpenCorrection}
          />

          {/* Review Queue & Exceptions (Human-in-the-Loop) */}
          <ReviewQueue
            queue={reviewQueue}
            exceptions={exceptions}
            actionLoading={actionLoading}
            onResolveAction={(act) => handleResumeWorkflow(act)}
            onOpenCorrection={() => handleOpenCorrection()}
          />

          {/* Recommendation Card */}
          <RecommendationCard recommendation={activeRecommendation} history={history} />

          {/* Approval / Rejection Governance Panel */}
          <ApprovalPanel
            recommendation={activeRecommendation}
            loading={actionLoading}
            onApprove={handleApprove}
            onReject={handleReject}
          />
        </>
      )}

      {/* Evidence Citation Slide-Over Drawer */}
      <EvidenceDrawer
        open={evidenceDrawerOpen}
        record={selectedEvidenceRecord}
        onClose={() => setEvidenceDrawerOpen(false)}
      />

      {/* Line Correction Modal */}
      <CorrectionForm
        open={correctionModalOpen}
        record={correctionRecord}
        loading={actionLoading}
        onClose={() => setCorrectionModalOpen(false)}
        onSubmit={handleSubmitCorrection}
      />
    </DashboardContent>
  );
}
