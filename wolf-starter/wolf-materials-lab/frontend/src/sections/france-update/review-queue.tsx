import type { ExceptionItem, ReviewQueueItem } from 'src/api/types';

import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import Stack from '@mui/material/Stack';
import Button from '@mui/material/Button';
import Typography from '@mui/material/Typography';
import CardHeader from '@mui/material/CardHeader';

import { Label } from 'src/components/label';
import { Iconify } from 'src/components/iconify';

// ----------------------------------------------------------------------

interface ReviewQueueProps {
  queue: ReviewQueueItem[];
  exceptions: ExceptionItem[];
  actionLoading?: boolean;
  onResolveAction: (action: string) => void;
  onOpenCorrection?: () => void;
}

export function ReviewQueue({
  queue,
  exceptions,
  actionLoading = false,
  onResolveAction,
  onOpenCorrection,
}: ReviewQueueProps) {
  const hasQueueItems = queue.length > 0;
  const hasExceptions = exceptions.length > 0;

  if (!hasQueueItems && !hasExceptions) {
    return (
      <Card sx={{ mb: 3 }}>
        <CardHeader title="Review Queue & Exceptions" subheader="Active blocking items and warnings" />
        <Box sx={{ p: 3, textAlign: 'center' }}>
          <Iconify icon="solar:check-circle-bold" width={36} sx={{ color: 'success.main', mb: 1 }} />
          <Typography variant="subtitle1">No Pending Review Blockers</Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary' }}>
            All incoming records for the France update have passed extraction and validation rules.
          </Typography>
        </Box>
      </Card>
    );
  }

  return (
    <Card sx={{ mb: 3 }}>
      <CardHeader
        title="Review Queue & Exceptions"
        subheader={`${queue.length} review item(s) awaiting buyer resolution | ${exceptions.length} warning(s)`}
        action={
          hasQueueItems ? (
            <Label color="warning" variant="filled">
              Awaiting Action
            </Label>
          ) : (
            <Label color="success">Clear</Label>
          )
        }
      />

      <Box sx={{ p: 3 }}>
        {/* Paused Review Item */}
        {queue.map((item) => (
          <Box
            key={item.run_id}
            sx={{
              p: 2,
              mb: 2,
              borderRadius: 1.5,
              border: '1px solid',
              borderColor: 'warning.light',
              bgcolor: 'warning.lighter',
            }}
          >
            <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1.5 }}>
              <Stack direction="row" alignItems="center" spacing={1}>
                <Iconify icon="solar:danger-triangle-bold" sx={{ color: 'warning.dark' }} />
                <Typography variant="subtitle2" sx={{ color: 'warning.darker' }}>
                  Workflow Paused: Review Required Before Final Recommendation
                </Typography>
              </Stack>
              <Label color="warning">{item.stage}</Label>
            </Stack>

            <Typography variant="body2" sx={{ color: 'warning.darker', mb: 2 }}>
              The agent workflow verified spend extraction and detected replacement scope. Buyer
              confirmation is required to proceed or record line corrections.
            </Typography>

            {item.blocking_issues.length > 0 && (
              <Box sx={{ mb: 2 }}>
                <Typography variant="caption" sx={{ fontWeight: 700, color: 'warning.darker' }}>
                  Issues:
                </Typography>
                <Stack spacing={0.5} sx={{ mt: 0.5 }}>
                  {item.blocking_issues.map((iss, idx) => (
                    <Typography key={idx} variant="caption" sx={{ color: 'warning.darker' }}>
                      • {iss}
                    </Typography>
                  ))}
                </Stack>
              </Box>
            )}

            <Stack direction="row" spacing={1.5} sx={{ mt: 1 }}>
              {item.allowed_actions.includes('continue_to_approval_phase') && (
                <Button
                  size="small"
                  variant="contained"
                  color="warning"
                  startIcon={<Iconify icon="solar:check-read-bold" />}
                  onClick={() => onResolveAction('continue_to_approval_phase')}
                  disabled={actionLoading}
                >
                  Accept Scope & Continue to Approval
                </Button>
              )}

              {item.allowed_actions.includes('accept_scope') &&
                !item.allowed_actions.includes('continue_to_approval_phase') && (
                  <Button
                    size="small"
                    variant="contained"
                    color="warning"
                    onClick={() => onResolveAction('accept_scope')}
                    disabled={actionLoading}
                  >
                    Accept Scope
                  </Button>
                )}

              {onOpenCorrection && (
                <Button
                  size="small"
                  variant="outlined"
                  color="inherit"
                  startIcon={<Iconify icon="solar:pen-bold" />}
                  onClick={onOpenCorrection}
                  disabled={actionLoading}
                >
                  Submit Line Correction
                </Button>
              )}
            </Stack>
          </Box>
        ))}

        {/* Structured Exceptions List */}
        {hasExceptions && (
          <Box sx={{ mt: 2 }}>
            <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 700, mb: 1, display: 'block' }}>
              RECONCILIATION EXCEPTIONS & WARNINGS
            </Typography>
            <Stack spacing={1}>
              {exceptions.map((exc) => (
                <Stack
                  key={exc.id}
                  direction="row"
                  alignItems="center"
                  justifyContent="space-between"
                  sx={{
                    p: 1.5,
                    borderRadius: 1,
                    border: '1px solid',
                    borderColor: 'divider',
                  }}
                >
                  <Stack direction="row" alignItems="center" spacing={1}>
                    <Iconify
                      icon={
                        exc.severity === 'error'
                          ? 'solar:close-circle-bold'
                          : 'solar:info-circle-bold'
                      }
                      sx={{
                        color: exc.severity === 'error' ? 'error.main' : 'info.main',
                      }}
                    />
                    <Typography variant="body2">{exc.message}</Typography>
                  </Stack>
                  <Label color={exc.severity === 'error' ? 'error' : 'info'}>
                    {exc.code}
                  </Label>
                </Stack>
              ))}
            </Stack>
          </Box>
        )}
      </Box>
    </Card>
  );
}
