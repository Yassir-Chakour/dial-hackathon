import type { ChangeRecordItem, RecommendationChangesResponse } from 'src/api/types';

import { useMemo, useState } from 'react';

import Box from '@mui/material/Box';
import Tab from '@mui/material/Tab';
import Card from '@mui/material/Card';
import Tabs from '@mui/material/Tabs';
import Table from '@mui/material/Table';
import Button from '@mui/material/Button';
import TableRow from '@mui/material/TableRow';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import Typography from '@mui/material/Typography';
import CardHeader from '@mui/material/CardHeader';
import TableContainer from '@mui/material/TableContainer';

import { formatCurrency, getChangeTypeBadgeColor } from 'src/lib/formatters';

import { Label } from 'src/components/label';
import { Iconify } from 'src/components/iconify';
import { Scrollbar } from 'src/components/scrollbar';

// ----------------------------------------------------------------------

interface ChangeSetTableProps {
  changes: RecommendationChangesResponse | null;
  onSelectEvidence: (record: ChangeRecordItem) => void;
  onOpenCorrection?: (record: ChangeRecordItem) => void;
}

export function ChangeSetTable({
  changes,
  onSelectEvidence,
  onOpenCorrection,
}: ChangeSetTableProps) {
  const [activeTab, setActiveTab] = useState<string>('all');

  const taggedRecords = useMemo(() => {
    if (!changes) return [];

    const list: (ChangeRecordItem & { changeType: string })[] = [];

    (changes.added || []).forEach((r) => list.push({ ...r, changeType: 'added' }));
    (changes.replaced || []).forEach((r) => list.push({ ...r, changeType: 'replaced' }));
    (changes.preserved || []).forEach((r) => list.push({ ...r, changeType: 'preserved' }));
    (changes.removed_from_current || []).forEach((r) =>
      list.push({ ...r, changeType: 'removed_from_current' })
    );

    return list;
  }, [changes]);

  const filteredRecords = useMemo(() => {
    if (activeTab === 'all') return taggedRecords;
    return taggedRecords.filter((r) => r.changeType === activeTab);
  }, [taggedRecords, activeTab]);

  return (
    <Card sx={{ mb: 3 }}>
      <CardHeader
        title="Reconciled Spend Change Sets"
        subheader={`Review itemized line changes between v1 and incoming v2 (${taggedRecords.length} total rows)`}
      />

      <Tabs
        value={activeTab}
        onChange={(_, val) => setActiveTab(val)}
        sx={{ px: 2.5, borderBottom: '1px solid', borderColor: 'divider' }}
      >
        <Tab label={`All (${taggedRecords.length})`} value="all" />
        <Tab label={`Added (${changes?.added?.length || 0})`} value="added" />
        <Tab label={`Replaced (${changes?.replaced?.length || 0})`} value="replaced" />
        <Tab label={`Preserved (${changes?.preserved?.length || 0})`} value="preserved" />
        {changes?.removed_from_current?.length ? (
          <Tab
            label={`Removed (${changes.removed_from_current.length})`}
            value="removed_from_current"
          />
        ) : null}
      </Tabs>

      <TableContainer sx={{ position: 'relative' }}>
        <Scrollbar>
          <Table size="small" sx={{ minWidth: 780 }}>
            <TableHead>
              <TableRow>
                <TableCell>Change Type</TableCell>
                <TableCell>Product / Item</TableCell>
                <TableCell>Supplier</TableCell>
                <TableCell align="right">Previous Value</TableCell>
                <TableCell align="right">New Value</TableCell>
                <TableCell>Reason Code</TableCell>
                <TableCell align="center">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {filteredRecords.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} sx={{ textAlign: 'center', py: 4 }}>
                    <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                      No record changes in this category.
                    </Typography>
                  </TableCell>
                </TableRow>
              ) : (
                filteredRecords.map((row, idx) => (
                  <TableRow key={`${row.record_key || idx}-${row.changeType}`} hover>
                    <TableCell>
                      <Label color={getChangeTypeBadgeColor(row.changeType)}>
                        {row.changeType.replace('_', ' ').toUpperCase()}
                      </Label>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {row.product || row.record_key || '—'}
                      </Typography>
                      {row.record_key && row.product && (
                        <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                          {row.record_key}
                        </Typography>
                      )}
                    </TableCell>
                    <TableCell>{row.supplier || '—'}</TableCell>
                    <TableCell align="right">
                      {row.old_value !== undefined ? formatCurrency(row.old_value, row.currency || 'EUR') : '—'}
                    </TableCell>
                    <TableCell align="right">
                      {row.new_value !== undefined ? formatCurrency(row.new_value, row.currency || 'EUR') : '—'}
                    </TableCell>
                    <TableCell>
                      <Typography variant="caption" sx={{ fontFamily: 'monospace' }}>
                        {row.reason_code || 'reconciled_line'}
                      </Typography>
                    </TableCell>
                    <TableCell align="center">
                      <Box sx={{ display: 'flex', justifyContent: 'center', gap: 1 }}>
                        <Button
                          size="small"
                          variant="outlined"
                          color="inherit"
                          startIcon={<Iconify icon="solar:document-text-bold" width={14} />}
                          onClick={() => onSelectEvidence(row)}
                        >
                          Evidence
                        </Button>
                        {onOpenCorrection && (
                          <Button
                            size="small"
                            variant="soft"
                            color="warning"
                            startIcon={<Iconify icon="solar:pen-bold" width={14} />}
                            onClick={() => onOpenCorrection(row)}
                          >
                            Correct
                          </Button>
                        )}
                      </Box>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </Scrollbar>
      </TableContainer>
    </Card>
  );
}
