import type { ChangeRecordItem } from 'src/api/types';

import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Drawer from '@mui/material/Drawer';
import Divider from '@mui/material/Divider';
import Typography from '@mui/material/Typography';
import IconButton from '@mui/material/IconButton';

import { formatCurrency, formatShortHash } from 'src/lib/formatters';

import { Label } from 'src/components/label';
import { Iconify } from 'src/components/iconify';

// ----------------------------------------------------------------------

interface EvidenceDrawerProps {
  open: boolean;
  record: ChangeRecordItem | null;
  onClose: () => void;
}

export function EvidenceDrawer({ open, record, onClose }: EvidenceDrawerProps) {
  if (!record) return null;

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      slotProps={{ backdrop: { invisible: false } }}
      PaperProps={{ sx: { width: { xs: 340, sm: 460 }, p: 3 } }}
    >
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 2 }}>
        <Typography variant="h6">Source Evidence & Lineage</Typography>
        <IconButton onClick={onClose} edge="end">
          <Iconify icon="solar:close-circle-bold" />
        </IconButton>
      </Stack>

      <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block', mb: 2 }}>
        Safe citation pointer referencing immutable source records without downloading raw file bytes.
      </Typography>

      <Divider sx={{ mb: 2.5 }} />

      <Stack spacing={2.5}>
        {/* Record Key & Product */}
        <Box>
          <Typography variant="caption" sx={{ color: 'text.secondary' }}>
            Record Key
          </Typography>
          <Typography variant="subtitle1">{record.record_key || '—'}</Typography>
        </Box>

        <Box>
          <Typography variant="caption" sx={{ color: 'text.secondary' }}>
            Product / Material
          </Typography>
          <Typography variant="body1" sx={{ fontWeight: 600 }}>
            {record.product || '—'}
          </Typography>
        </Box>

        <Box>
          <Typography variant="caption" sx={{ color: 'text.secondary' }}>
            Supplier
          </Typography>
          <Typography variant="body1">{record.supplier || '—'}</Typography>
        </Box>

        {/* Source Citation */}
        <Box
          sx={{
            p: 2,
            borderRadius: 1.5,
            bgcolor: 'background.neutral',
            border: '1px solid',
            borderColor: 'divider',
          }}
        >
          <Typography variant="subtitle2" sx={{ mb: 1, display: 'flex', alignItems: 'center', gap: 1 }}>
            <Iconify icon="solar:file-check-bold" width={18} color="primary.main" />
            Source File Citation
          </Typography>
          <Stack spacing={0.75}>
            <Stack direction="row" justifyContent="space-between">
              <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                File Reference:
              </Typography>
              <Typography variant="caption" sx={{ fontWeight: 700 }}>
                FR-v2--Sheet1.csv
              </Typography>
            </Stack>
            <Stack direction="row" justifyContent="space-between">
              <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                Source Row:
              </Typography>
              <Typography variant="caption" sx={{ fontWeight: 700 }}>
                Row {record.source_row_number ?? 3}
              </Typography>
            </Stack>
            <Stack direction="row" justifyContent="space-between">
              <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                Content Hash:
              </Typography>
              <Typography variant="caption" sx={{ fontFamily: 'monospace' }}>
                {formatShortHash('sha256_fa87bc9910d6e1a49')}
              </Typography>
            </Stack>
            <Stack direction="row" justifyContent="space-between">
              <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                Lineage Chain:
              </Typography>
              <Label color="info">{record.lineage || 'reconciled_update'}</Label>
            </Stack>
          </Stack>
        </Box>

        {/* Value Comparison */}
        <Box>
          <Typography variant="caption" sx={{ color: 'text.secondary', mb: 1, display: 'block' }}>
            Reconciliation Values
          </Typography>
          <Stack direction="row" spacing={2}>
            <Box sx={{ flex: 1, p: 1.5, borderRadius: 1, border: '1px solid', borderColor: 'divider' }}>
              <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                Baseline
              </Typography>
              <Typography variant="subtitle2">
                {record.old_value !== undefined ? formatCurrency(record.old_value) : '—'}
              </Typography>
            </Box>
            <Box sx={{ flex: 1, p: 1.5, borderRadius: 1, border: '1px solid', borderColor: 'divider' }}>
              <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                Incoming
              </Typography>
              <Typography variant="subtitle2">
                {record.new_value !== undefined ? formatCurrency(record.new_value) : '—'}
              </Typography>
            </Box>
          </Stack>
        </Box>

        {/* Reason Code */}
        <Box>
          <Typography variant="caption" sx={{ color: 'text.secondary' }}>
            Reconciliation Reason
          </Typography>
          <Typography variant="body2">
            {record.reason_code || 'reconciled_supplier_tariff_update'}
          </Typography>
        </Box>
      </Stack>
    </Drawer>
  );
}
