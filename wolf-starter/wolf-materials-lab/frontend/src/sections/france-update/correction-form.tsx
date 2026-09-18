import type { ChangeRecordItem, SubmitCorrectionRequest } from 'src/api/types';

import { useState, useEffect } from 'react';

import Stack from '@mui/material/Stack';
import Alert from '@mui/material/Alert';
import Dialog from '@mui/material/Dialog';
import Button from '@mui/material/Button';
import MenuItem from '@mui/material/MenuItem';
import TextField from '@mui/material/TextField';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';

// ----------------------------------------------------------------------

const ALLOWED_FIELDS = [
  { value: 'unit_price', label: 'Unit Price' },
  { value: 'quantity', label: 'Quantity' },
  { value: 'value', label: 'Line Value' },
  { value: 'supplier', label: 'Supplier Name' },
  { value: 'currency', label: 'Currency' },
  { value: 'product', label: 'Product Key' },
];

interface CorrectionFormProps {
  open: boolean;
  record: ChangeRecordItem | null;
  loading?: boolean;
  onClose: () => void;
  onSubmit: (payload: SubmitCorrectionRequest) => Promise<void>;
}

export function CorrectionForm({
  open,
  record,
  loading = false,
  onClose,
  onSubmit,
}: CorrectionFormProps) {
  const [fieldName, setFieldName] = useState<string>('unit_price');
  const [correctedValue, setCorrectedValue] = useState<string>('');
  const [reason, setReason] = useState<string>('');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    if (record) {
      setFieldName('unit_price');
      setCorrectedValue(record.new_value !== undefined ? String(record.new_value) : '');
      setReason('');
      setErrorMsg(null);
    }
  }, [record]);

  const handleSubmit = async () => {
    if (!correctedValue.trim()) {
      setErrorMsg('Please provide a corrected value.');
      return;
    }
    if (!reason.trim()) {
      setErrorMsg('A specific reason is required for procurement audit compliance.');
      return;
    }

    const sourceRecordId =
      record?.source_record_id || record?.record_key || 'sr_txn_placeholder';

    try {
      await onSubmit({
        source_record_id: sourceRecordId,
        field_name: fieldName,
        original_value: record?.new_value !== undefined ? String(record.new_value) : null,
        corrected_value: correctedValue.trim(),
        reason: reason.trim(),
      });
      onClose();
    } catch {
      // Error handled by parent feedback
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Submit Reviewer Line Correction</DialogTitle>

      <DialogContent dividers>
        <Stack spacing={2.5}>
          <Alert severity="info">
            <strong>Append-Only Audit Guarantee:</strong> Original source records are never mutated
            in place. This correction creates a versioned audit record and triggers recommendation
            review.
          </Alert>

          {errorMsg && <Alert severity="error">{errorMsg}</Alert>}

          <TextField
            label="Target Record Reference"
            value={record?.record_key || record?.product || 'Selected Record'}
            disabled
            fullWidth
          />

          <TextField
            select
            label="Field to Correct"
            value={fieldName}
            onChange={(e) => setFieldName(e.target.value)}
            fullWidth
          >
            {ALLOWED_FIELDS.map((opt) => (
              <MenuItem key={opt.value} value={opt.value}>
                {opt.label}
              </MenuItem>
            ))}
          </TextField>

          <TextField
            label="Original Value (Current)"
            value={record?.new_value !== undefined ? String(record.new_value) : '—'}
            disabled
            fullWidth
          />

          <TextField
            label="Corrected Value"
            value={correctedValue}
            onChange={(e) => setCorrectedValue(e.target.value)}
            placeholder="e.g. 2475.64 or sup-novex"
            fullWidth
            required
          />

          <TextField
            label="Audit Reason & Citation Reference"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="e.g. Reviewer confirmed invoice cell B4 tariff discount"
            multiline
            rows={3}
            fullWidth
            required
            helperText="Maximum 1,000 characters. Recorded in immutable audit log."
          />
        </Stack>
      </DialogContent>

      <DialogActions>
        <Button color="inherit" onClick={onClose} disabled={loading}>
          Cancel
        </Button>
        <Button
          variant="contained"
          color="primary"
          onClick={handleSubmit}
          disabled={loading || !correctedValue || !reason}
        >
          {loading ? 'Submitting…' : 'Submit Correction'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
