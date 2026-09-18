import type { RecommendationDetail } from 'src/api/types';

import { useState } from 'react';

import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import Stack from '@mui/material/Stack';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import CardHeader from '@mui/material/CardHeader';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';

import { formatShortHash } from 'src/lib/formatters';

import { Iconify } from 'src/components/iconify';

// ----------------------------------------------------------------------

interface ApprovalPanelProps {
  recommendation: RecommendationDetail | null;
  loading?: boolean;
  onApprove: (reason?: string) => Promise<void>;
  onReject: (reason: string) => Promise<void>;
}

export function ApprovalPanel({
  recommendation,
  loading = false,
  onApprove,
  onReject,
}: ApprovalPanelProps) {
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState('');

  if (!recommendation) return null;

  const isApproved = recommendation.status === 'approved';
  const isRejected = recommendation.status === 'rejected';
  const isStale = recommendation.status === 'stale';
  const allowedActions = recommendation.allowed_actions || [];
  const canApprove = allowedActions.includes('approve') && !isApproved && !isStale;
  const canReject = allowedActions.includes('reject') && !isRejected;

  const handleConfirmReject = async () => {
    if (!rejectReason.trim()) return;
    await onReject(rejectReason.trim());
    setRejectOpen(false);
    setRejectReason('');
  };

  return (
    <Card sx={{ mb: 3 }}>
      <CardHeader
        title="Buyer Governance & Approval Boundary"
        subheader="Commit exact recommendation version with optimistic concurrency hash check"
      />

      <Box sx={{ p: 3 }}>
        {isStale && (
          <Alert severity="error" sx={{ mb: 2 }}>
            <strong>Approval Blocked (Stale Hash):</strong> The recommendation has been superseded
            by newer spend records. The server will reject approval with 409 Conflict.
          </Alert>
        )}

        {isApproved && (
          <Alert severity="success" sx={{ mb: 2 }}>
            <strong>Version Approved:</strong> This recommendation version is committed. Mock external
            procurement action prepared.
          </Alert>
        )}

        {isRejected && (
          <Alert severity="warning" sx={{ mb: 2 }}>
            <strong>Recommendation Rejected:</strong> Preserved in immutable audit history.
          </Alert>
        )}

        <Stack
          direction={{ xs: 'column', sm: 'row' }}
          alignItems={{ xs: 'flex-start', sm: 'center' }}
          justifyContent="space-between"
          spacing={2}
        >
          <Box>
            <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block' }}>
              Commit Precondition:
            </Typography>
            <Typography variant="body2" sx={{ fontWeight: 600 }}>
              Expected Calculation Hash:{' '}
              <Typography component="span" variant="caption" sx={{ fontFamily: 'monospace' }}>
                {formatShortHash(recommendation.calculation_hash, 10)}
              </Typography>
            </Typography>
          </Box>

          <Stack direction="row" spacing={1.5}>
            {canReject && (
              <Button
                variant="outlined"
                color="error"
                startIcon={<Iconify icon="solar:close-circle-bold" />}
                onClick={() => setRejectOpen(true)}
                disabled={loading}
              >
                Reject Update
              </Button>
            )}

            <Button
              variant="contained"
              color="success"
              size="large"
              startIcon={<Iconify icon="solar:check-circle-bold" />}
              onClick={() => onApprove()}
              disabled={loading || !canApprove}
            >
              {loading ? 'Committing…' : isApproved ? 'Already Approved' : 'Approve Current Version'}
            </Button>
          </Stack>
        </Stack>
      </Box>

      {/* Reject Modal */}
      <Dialog open={rejectOpen} onClose={() => setRejectOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>Reject Procurement Recommendation</DialogTitle>
        <DialogContent dividers>
          <Typography variant="body2" sx={{ mb: 2, color: 'text.secondary' }}>
            Please state the procurement compliance or business reason for rejecting this version.
          </Typography>
          <TextField
            label="Rejection Reason"
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            multiline
            rows={3}
            fullWidth
            required
            autoFocus
          />
        </DialogContent>
        <DialogActions>
          <Button color="inherit" onClick={() => setRejectOpen(false)}>
            Cancel
          </Button>
          <Button
            variant="contained"
            color="error"
            onClick={handleConfirmReject}
            disabled={!rejectReason.trim() || loading}
          >
            Confirm Rejection
          </Button>
        </DialogActions>
      </Dialog>
    </Card>
  );
}
