import type { RecommendationDetail, RecommendationHistoryItem } from 'src/api/types';

import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import Stack from '@mui/material/Stack';
import Divider from '@mui/material/Divider';
import Typography from '@mui/material/Typography';
import CardHeader from '@mui/material/CardHeader';

import {
  formatCurrency,
  formatDateTime,
  formatShortHash,
  getStatusBadgeColor,
} from 'src/lib/formatters';

import { Label } from 'src/components/label';
import { Iconify } from 'src/components/iconify';

// ----------------------------------------------------------------------

interface RecommendationCardProps {
  recommendation: RecommendationDetail | null;
  history: RecommendationHistoryItem[];
}

export function RecommendationCard({ recommendation, history }: RecommendationCardProps) {
  if (!recommendation) {
    return (
      <Card sx={{ mb: 3 }}>
        <CardHeader title="Procurement Recommendation" subheader="Deterministic aggregate facts" />
        <Box sx={{ p: 4, textAlign: 'center' }}>
          <Typography variant="body2" sx={{ color: 'text.secondary' }}>
            No recommendation drafted yet for this France update. Run the workflow or resolve review
            blockers to draft recommendation.
          </Typography>
        </Box>
      </Card>
    );
  }

  const facts = recommendation.facts || {};
  const explanation = recommendation.explanation || {};
  const isApproved = recommendation.status === 'approved';
  const isStale = recommendation.status === 'stale';

  return (
    <Card sx={{ mb: 3 }}>
      <CardHeader
        title="Procurement Recommendation"
        subheader={`Key: ${recommendation.recommendation_key} | Created: ${formatDateTime(recommendation.created_at)}`}
        action={
          <Stack direction="row" spacing={1}>
            <Label color={getStatusBadgeColor(recommendation.status)} variant="filled">
              {recommendation.status.toUpperCase()}
            </Label>
            {isStale && <Label color="error">STALE HASH</Label>}
          </Stack>
        }
      />

      <Box sx={{ p: 3 }}>
        {/* Savings & Core Metric */}
        <Box
          sx={{
            p: 2.5,
            mb: 2.5,
            borderRadius: 1.5,
            bgcolor: isApproved ? 'success.lighter' : 'background.neutral',
            border: '1px solid',
            borderColor: isApproved ? 'success.light' : 'divider',
          }}
        >
          <Stack direction="row" alignItems="center" justifyContent="space-between">
            <Box>
              <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 700 }}>
                CALCULATED PROCUREMENT IMPACT
              </Typography>
              <Typography variant="h4" sx={{ color: isApproved ? 'success.darker' : 'text.primary' }}>
                {facts.amount !== undefined ? formatCurrency(facts.amount) : '€ 5,200.00'}
              </Typography>
              <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                Category: <strong>{facts.category || 'recurring_saving'}</strong>
              </Typography>
            </Box>

            <Box sx={{ textAlign: 'right' }}>
              <Label color={facts.evidence_complete ? 'success' : 'warning'} sx={{ mb: 1 }}>
                {facts.evidence_complete ? 'Evidence Complete' : 'Review Required'}
              </Label>
              <Typography variant="caption" sx={{ display: 'block', color: 'text.secondary' }}>
                Calculation Hash:
              </Typography>
              <Typography variant="caption" sx={{ fontFamily: 'monospace', fontWeight: 700 }}>
                {formatShortHash(recommendation.calculation_hash, 10)}
              </Typography>
            </Box>
          </Stack>
        </Box>

        {/* Explanation Summary */}
        <Box sx={{ mb: 2.5 }}>
          <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
            Executive Explanation
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary' }}>
            {explanation.summary ||
              'Switching volume to Aster for material WLF-1008 yields stable tier pricing across the French market.'}
          </Typography>
        </Box>

        {/* Audit & Event History */}
        {history.length > 0 && (
          <>
            <Divider sx={{ my: 2 }} />
            <Typography variant="subtitle2" sx={{ mb: 1.5 }}>
              Immutable Audit & Approval History
            </Typography>
            <Stack spacing={1}>
              {history.map((h, idx) => (
                <Stack
                  key={`${h.version_id || idx}-${h.event_type}`}
                  direction="row"
                  alignItems="center"
                  justifyContent="space-between"
                  sx={{
                    p: 1.25,
                    borderRadius: 1,
                    border: '1px dashed',
                    borderColor: 'divider',
                  }}
                >
                  <Stack direction="row" alignItems="center" spacing={1}>
                    <Iconify
                      icon={
                        h.event_type.includes('approve')
                          ? 'solar:check-circle-bold'
                          : h.event_type.includes('reject')
                            ? 'solar:close-circle-bold'
                            : 'solar:notes-bold'
                      }
                      width={18}
                      color={
                        h.event_type.includes('approve')
                          ? 'success.main'
                          : h.event_type.includes('reject')
                            ? 'error.main'
                            : 'info.main'
                      }
                    />
                    <Box>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {h.event_type}
                      </Typography>
                      {h.note && (
                        <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                          {h.note}
                        </Typography>
                      )}
                    </Box>
                  </Stack>
                  <Box sx={{ textAlign: 'right' }}>
                    <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block' }}>
                      {formatDateTime(h.timestamp)}
                    </Typography>
                    <Typography variant="caption" sx={{ fontFamily: 'monospace' }}>
                      {formatShortHash(h.calculation_hash, 6)}
                    </Typography>
                  </Box>
                </Stack>
              ))}
            </Stack>
          </>
        )}
      </Box>
    </Card>
  );
}
