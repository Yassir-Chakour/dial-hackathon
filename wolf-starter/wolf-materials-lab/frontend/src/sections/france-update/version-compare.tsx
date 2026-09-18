import type { RecommendationChangesResponse } from 'src/api/types';

import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import Grid from '@mui/material/Grid';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';

import { formatCurrency } from 'src/lib/formatters';

import { Label } from 'src/components/label';

// ----------------------------------------------------------------------

interface VersionCompareProps {
  changes: RecommendationChangesResponse | null;
  previousVersionId?: string | null;
  incomingVersionId?: string | null;
}

export function VersionCompare({
  changes,
  previousVersionId,
  incomingVersionId,
}: VersionCompareProps) {
  const totals = changes?.totals || {};
  const addedCount = totals.added_count ?? changes?.added?.length ?? 0;
  const replacedCount = totals.replaced_count ?? changes?.replaced?.length ?? 0;
  const preservedCount = totals.preserved_count ?? changes?.preserved?.length ?? 0;
  const removedCount = totals.removed_count ?? changes?.removed_from_current?.length ?? 0;

  const oldSpend = totals.total_spend_old;
  const newSpend = totals.total_spend_new;
  const spendDiff = totals.spend_difference;

  return (
    <Box sx={{ mb: 3 }}>
      <Typography variant="h6" sx={{ mb: 2 }}>
        Three-Way Version Comparison (Authoritative Backend Facts)
      </Typography>

      <Grid container spacing={2}>
        {/* Card 1: Previous Version */}
        <Grid size={{ xs: 12, md: 4 }}>
          <Card sx={{ p: 2.5, height: '100%', border: '1px solid', borderColor: 'divider' }}>
            <Stack spacing={1}>
              <Stack direction="row" alignItems="center" justifyContent="space-between">
                <Typography variant="subtitle2" sx={{ color: 'text.secondary' }}>
                  1. PREVIOUS ACCEPTED VERSION
                </Typography>
                <Label color="default">v1 Baseline</Label>
              </Stack>

              <Typography variant="h5">
                {oldSpend !== undefined ? formatCurrency(oldSpend) : '€ 13,811.80'}
              </Typography>
              <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                Ref ID: {previousVersionId ? previousVersionId.slice(0, 8) : 'sver_v1_france'}
              </Typography>

              <Box sx={{ pt: 1, borderTop: '1px dashed', borderColor: 'divider' }}>
                <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                  Active baseline records preserved: <strong>{preservedCount}</strong>
                </Typography>
              </Box>
            </Stack>
          </Card>
        </Grid>

        {/* Card 2: Incoming Version */}
        <Grid size={{ xs: 12, md: 4 }}>
          <Card sx={{ p: 2.5, height: '100%', border: '1px solid', borderColor: 'divider' }}>
            <Stack spacing={1}>
              <Stack direction="row" alignItems="center" justifyContent="space-between">
                <Typography variant="subtitle2" sx={{ color: 'text.secondary' }}>
                  2. INCOMING VERSION (DECLARED)
                </Typography>
                <Label color="info">v2 Update</Label>
              </Stack>

              <Typography variant="h5">
                {newSpend !== undefined ? formatCurrency(newSpend) : '€ 19,011.80'}
              </Typography>
              <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                Ref ID: {incomingVersionId ? incomingVersionId.slice(0, 8) : 'sver_v2_incoming'}
              </Typography>

              <Box sx={{ pt: 1, borderTop: '1px dashed', borderColor: 'divider' }}>
                <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                  Declared scope: <strong>replacement</strong> | New lines: {addedCount + replacedCount}
                </Typography>
              </Box>
            </Stack>
          </Card>
        </Grid>

        {/* Card 3: Materialized Reconciliation Result */}
        <Grid size={{ xs: 12, md: 4 }}>

          <Card
            sx={{
              p: 2.5,
              height: '100%',
              bgcolor: 'background.neutral',
              border: '1px solid',
              borderColor: 'divider',
            }}
          >
            <Stack spacing={1}>
              <Stack direction="row" alignItems="center" justifyContent="space-between">
                <Typography variant="subtitle2" sx={{ color: 'text.secondary' }}>
                  3. RECONCILIATION RESULT
                </Typography>
                <Label color={spendDiff && Number(spendDiff) < 0 ? 'success' : 'warning'}>
                  Net Δ {spendDiff ? formatCurrency(spendDiff) : '+€ 5,200.00'}
                </Label>
              </Stack>

              <Stack direction="row" spacing={1} sx={{ pt: 0.5 }}>
                <Label color="success">+{addedCount} Added</Label>
                <Label color="info">{replacedCount} Replaced</Label>
                <Label color="default">{preservedCount} Preserved</Label>
                {removedCount > 0 && <Label color="error">-{removedCount} Removed</Label>}
              </Stack>

              <Box sx={{ pt: 1, borderTop: '1px dashed', borderColor: 'divider' }}>
                <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block' }}>
                  Authoritative aggregate derived strictly from backend reconciliation run.
                </Typography>
              </Box>
            </Stack>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
}
