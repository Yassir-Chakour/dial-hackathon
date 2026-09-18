import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import CardHeader from '@mui/material/CardHeader';

import { Label } from 'src/components/label';
import { Iconify } from 'src/components/iconify';

// ----------------------------------------------------------------------

const STAGES = [
  { id: 'intake', label: '1. Intake' },
  { id: 'inspect', label: '2. Inspect' },
  { id: 'scope', label: '3. Scope' },
  { id: 'extract', label: '4. Extract' },
  { id: 'reconcile', label: '5. Reconcile' },
  { id: 'impact', label: '6. Impact' },
  { id: 'evidence', label: '7. Evidence' },
  { id: 'drafted', label: '8. Recommend' },
  { id: 'awaiting_review', label: '9. Review Pause' },
];

interface WorkflowTimelineProps {
  currentStage?: string;
  status?: string;
  runId?: string | null;
  history?: string[];
}

export function WorkflowTimeline({
  currentStage = 'intake',
  status = 'pending',
  runId,
  history = [],
}: WorkflowTimelineProps) {
  const currentIdx = STAGES.findIndex((s) => s.id === currentStage);
  const activeIdx = currentIdx >= 0 ? currentIdx : 0;

  return (
    <Card sx={{ mb: 3 }}>
      <CardHeader
        title="Agent Workflow Execution Pipeline"
        subheader={
          runId
            ? `Run ID: ${runId} | Status: ${status.toUpperCase()}`
            : 'No active workflow run selected'
        }
        action={
          <Label
            color={
              status === 'completed'
                ? 'success'
                : status === 'paused'
                  ? 'warning'
                  : status === 'failed'
                    ? 'error'
                    : 'info'
            }
          >
            {status}
          </Label>
        }
      />
      <Box sx={{ p: 3, overflowX: 'auto' }}>
        <Stack direction="row" spacing={1} alignItems="center" sx={{ minWidth: 720 }}>
          {STAGES.map((st, idx) => {
            const isCompleted = idx < activeIdx || status === 'completed';
            const isCurrent = idx === activeIdx && status !== 'completed';
            const isPaused = isCurrent && status === 'paused';

            return (
              <Stack
                key={st.id}
                direction="row"
                alignItems="center"
                spacing={1}
                sx={{ flex: 1, minWidth: 100 }}
              >
                <Box
                  sx={{
                    px: 1.5,
                    py: 1,
                    borderRadius: 1.5,
                    border: '1px solid',
                    borderColor: isPaused
                      ? 'warning.main'
                      : isCurrent
                        ? 'primary.main'
                        : isCompleted
                          ? 'success.light'
                          : 'divider',
                    bgcolor: isPaused
                      ? 'warning.lighter'
                      : isCurrent
                        ? 'primary.lighter'
                        : isCompleted
                          ? 'success.lighter'
                          : 'background.neutral',
                    color: isPaused
                      ? 'warning.darker'
                      : isCurrent
                        ? 'primary.darker'
                        : isCompleted
                          ? 'success.darker'
                          : 'text.disabled',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                    width: '100%',
                    textAlign: 'center',
                  }}
                >
                  <Iconify
                    icon={
                      isCompleted
                        ? 'solar:check-circle-bold'
                        : isPaused
                          ? 'solar:pause-circle-bold'
                          : isCurrent
                            ? 'solar:play-bold'
                            : 'solar:stop-circle-outline'
                    }
                    width={18}
                    sx={{ mb: 0.5 }}
                  />
                  <Typography variant="caption" sx={{ fontWeight: 700, fontSize: 11 }}>
                    {st.label}
                  </Typography>
                </Box>
                {idx < STAGES.length - 1 && (
                  <Iconify icon="solar:arrow-right-bold" width={14} sx={{ color: 'text.disabled' }} />
                )}
              </Stack>
            );
          })}
        </Stack>

        {/* History Breadcrumb snippet */}
        {history.length > 0 && (
          <Box sx={{ mt: 2, pt: 1.5, borderTop: '1px dashed', borderColor: 'divider' }}>
            <Typography variant="caption" sx={{ color: 'text.secondary' }}>
              Execution breadcrumbs: {history.slice(-4).join(' → ')}
            </Typography>
          </Box>
        )}
      </Box>
    </Card>
  );
}
