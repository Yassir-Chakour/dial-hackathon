import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Button from '@mui/material/Button';
import Typography from '@mui/material/Typography';

import { Label } from 'src/components/label';
import { Iconify } from 'src/components/iconify';

// ----------------------------------------------------------------------

interface UpdateHeaderProps {
  market: string;
  updateMode: string;
  status: string;
  isPolling?: boolean;
  actionLoading?: boolean;
  onStartDemo: () => void;
  onRefresh: () => void;
  onReplay?: () => void;
}

export function UpdateHeader({
  market,
  updateMode,
  status,
  isPolling = false,
  actionLoading = false,
  onStartDemo,
  onRefresh,
  onReplay,
}: UpdateHeaderProps) {
  return (
    <Box sx={{ mb: 3 }}>
      {/* Synthetic Banner */}
      <Box
        sx={{
          mb: 2,
          py: 0.75,
          px: 2,
          borderRadius: 1,
          bgcolor: 'warning.lighter',
          color: 'warning.darker',
          display: 'flex',
          alignItems: 'center',
          gap: 1,
        }}
      >
        <Iconify icon="solar:shield-warning-bold" width={20} />
        <Typography variant="caption" sx={{ fontWeight: 700 }}>
          SYNTHETIC BENCHMARK DATA: All supplier records, invoice references, and pricing in this
          France update scenario are simulated for evaluation.
        </Typography>
      </Box>

      {/* Main Header Title & Controls */}
      <Stack
        direction={{ xs: 'column', md: 'row' }}
        alignItems={{ xs: 'flex-start', md: 'center' }}
        justifyContent="space-between"
        spacing={2}
      >
        <Box>
          <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 0.5 }}>
            <Typography variant="h4">France Material Supply Update</Typography>
            <Label color="primary" variant="filled">
              {market}
            </Label>
            <Label color="info" variant="soft">
              {updateMode}
            </Label>
            {status && (
              <Label
                color={
                  ['approved', 'completed'].includes(status)
                    ? 'success'
                    : ['paused', 'awaiting_review', 'needs_review'].includes(status)
                      ? 'warning'
                      : ['failed', 'rejected'].includes(status)
                        ? 'error'
                        : 'default'
                }
              >
                {status}
              </Label>
            )}
          </Stack>
          <Typography variant="body2" sx={{ color: 'text.secondary' }}>
            Reviewable procurement update workflow connecting spend extraction, reconciliation, and
            governed buyer approvals.
          </Typography>
        </Box>

        <Stack direction="row" spacing={1.5}>
          <Button
            variant="outlined"
            color="inherit"
            startIcon={
              <Iconify
                icon="solar:restart-bold"
                sx={{ ...(isPolling && { animation: 'spin 2s linear infinite' }) }}
              />
            }
            onClick={onRefresh}
            disabled={actionLoading}
          >
            Refresh
          </Button>

          {onReplay && (
            <Button
              variant="outlined"
              color="info"
              startIcon={<Iconify icon="solar:history-bold" />}
              onClick={onReplay}
              disabled={actionLoading}
            >
              Replay Check
            </Button>
          )}

          <Button
            variant="contained"
            color="primary"
            startIcon={<Iconify icon="solar:play-circle-bold" />}
            onClick={onStartDemo}
            disabled={actionLoading}
          >
            Run Demo Update
          </Button>
        </Stack>
      </Stack>
    </Box>
  );
}
