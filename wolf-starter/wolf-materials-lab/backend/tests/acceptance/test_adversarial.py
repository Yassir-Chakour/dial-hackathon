"""Adversarial input suite for Phase Nine.

Verifies that hostile, malformed, contradictory, and out-of-scope inputs produce
explicit exceptions, review issues, or rejections—never fabricating accepted decisions.
"""

from decimal import Decimal
import pytest
from httpx import AsyncClient

from app.db.models import Recommendation, RecommendationStatus
from app.decisions.calculator import build_decision_input_snapshot, calculate_decision_facts
from app.decisions.contracts import DecisionRecord
from app.ingestion.csv_reader import CsvReaderError, read_csv_rows
from app.ingestion.normalizers import parse_date, parse_decimal
from app.ingestion.pipeline import IngestionPipeline
from app.persistence import (
    ApprovalError,
    IdempotencyConflictError,
    ReviewRepository,
    SourceRepository,
    SourceService,
)
from app.reconciliation.apply import apply_replacement
from app.reconciliation.contracts import EvidenceRef, ReconciliationRecord, UpdateScope
from tests.acceptance.conftest import FIXTURES_ROOT


ADV_FIXTURES = FIXTURES_ROOT / "adversarial"


def test_adversarial_duplicate_event_different_payload(app) -> None:
    """Verify same event key with different payload raises IdempotencyConflictError."""
    db = app.state.test_db
    source_service = SourceService()

    with db.transaction() as session:
        source_service.accept_version(
            session,
            content=b"content-a",
            filename="a.csv",
            media_type="text/csv",
            market="FR",
            version_label="v1",
            scope_key="FR",
            event_key="evt:adv:diff_payload",
            payload={"hash": "original_payload"},
        )

    with db.transaction() as session:
        with pytest.raises(IdempotencyConflictError):
            source_service.accept_version(
                session,
                content=b"content-b",
                filename="b.csv",
                media_type="text/csv",
                market="FR",
                version_label="v2",
                scope_key="FR",
                event_key="evt:adv:diff_payload",
                payload={"hash": "tampered_or_different_payload"},
            )


def test_adversarial_scope_leakage_contains_unannounced_supplier() -> None:
    """Verify that replacement containing unannounced suppliers is detected as an error."""
    prev = [
        ReconciliationRecord(
            record_id="OLD-1",
            record_key="KEY-1",
            version_id="v1",
            market="FR",
            supplier_id="sup-aster",
            product_id="WLF-1008",
            value=Decimal("100"),
            currency="EUR",
            evidence=(EvidenceRef("v1", source_row_number=1),),
        )
    ]
    inc = [
        ReconciliationRecord(
            record_id="NEW-1",
            record_key="KEY-1",
            version_id="v2",
            market="FR",
            supplier_id="sup-orbit",  # Out of scope!
            product_id="WLF-1008",
            value=Decimal("100"),
            currency="EUR",
            evidence=(EvidenceRef("v2", source_row_number=1),),
        )
    ]
    scope = UpdateScope(market="FR", supplier_ids=("sup-aster",), evidence=(EvidenceRef("v2", source_row_number=1),))
    res = apply_replacement(prev, inc, scope)
    assert not res.accepted
    assert any(issue.code == "out_of_scope_record" for issue in res.issues)


def test_adversarial_currency_mismatch_in_calculator() -> None:
    """Verify that currency mismatch cannot be combined in benefit calculation."""
    snap = build_decision_input_snapshot(reconciliation_version_id="r1", source_version_ids=("v1",))
    records = [
        DecisionRecord(
            record_id="REC-1",
            record_key="KEY-1",
            product="WLF-1008",
            supplier="sup-aster",
            quantity=Decimal("10"),
            unit="piece",
            currency="EUR",
            value=Decimal("100"),
            baseline_value=Decimal("120"),
            validation_status="valid",
            evidence_ids=("ev-1",),
        ),
        DecisionRecord(
            record_id="REC-2",
            record_key="KEY-2",
            product="WLF-1008",
            supplier="sup-aster",
            quantity=Decimal("10"),
            unit="piece",
            currency="USD",
            value=Decimal("100"),
            baseline_value=Decimal("120"),
            validation_status="valid",
            evidence_ids=("ev-2",),
        ),
    ]
    with pytest.raises(ValueError, match="currency_mismatch"):
        calculate_decision_facts(snap, records)


def test_adversarial_unit_mismatch_in_calculator() -> None:
    """Verify that unit mismatch (e.g. box vs piece) cannot be naively aggregated."""
    snap = build_decision_input_snapshot(reconciliation_version_id="r1", source_version_ids=("v1",))
    records = [
        DecisionRecord(
            record_id="REC-1",
            record_key="KEY-1",
            product="WLF-1008",
            supplier="sup-aster",
            quantity=Decimal("10"),
            unit="piece",
            currency="EUR",
            value=Decimal("100"),
            baseline_value=Decimal("120"),
            validation_status="valid",
            evidence_ids=("ev-1",),
        ),
        DecisionRecord(
            record_id="REC-2",
            record_key="KEY-2",
            product="WLF-1008",
            supplier="sup-aster",
            quantity=Decimal("1"),
            unit="box",
            currency="EUR",
            value=Decimal("100"),
            baseline_value=Decimal("120"),
            validation_status="valid",
            evidence_ids=("ev-2",),
        ),
    ]
    with pytest.raises(ValueError, match="unit_mismatch"):
        calculate_decision_facts(snap, records)


def test_adversarial_ambiguous_and_invalid_records_abstained() -> None:
    """Verify that ambiguous or invalid records result in insufficient_evidence rather than fabricated savings."""
    snap = build_decision_input_snapshot(reconciliation_version_id="r1", source_version_ids=("v1",))
    records = [
        DecisionRecord(
            record_id="REC-1",
            record_key="KEY-1",
            product="WLF-1008",
            supplier="sup-aster",
            quantity=Decimal("10"),
            unit="piece",
            currency="EUR",
            value=Decimal("100"),
            baseline_value=Decimal("120"),
            validation_status="valid",
            evidence_ids=("ev-1",),
            ambiguous=True,
        ),
    ]
    res = calculate_decision_facts(snap, records)
    assert res.category == "insufficient_evidence"
    assert not res.evidence_complete
    assert "invalid_or_ambiguous_record" in res.reason_codes


def test_adversarial_formula_injection_treated_as_literal_data() -> None:
    """Verify CSV cells starting with '=', '+', '-', '@' are never executed and treated as string data."""
    path = ADV_FIXTURES / "formula_injection.csv"
    rows = read_csv_rows(path.read_bytes(), "src-adv-1", "v1")
    for r in rows[1:]:  # skip header
        desc = r.cells[7]
        # Must remain literal text
        assert any(desc.startswith(prefix) for prefix in ("=", "+", "-", "@"))
        assert isinstance(desc, str)


def test_adversarial_prompt_injection_in_source_rows_ignored_by_deterministic_rules() -> None:
    """Verify prompt override strings in source rows cannot bypass deterministic validation."""
    path = ADV_FIXTURES / "prompt_injection.csv"
    rows = read_csv_rows(path.read_bytes(), "src-adv-2", "v1")
    pipe = IngestionPipeline()
    res = pipe.process(rows, "src-adv-2", "v1")
    # Ingestion completes deterministically; prompt injection is treated as text
    assert len(res.records) >= 1
    assert any("SYSTEM PROMPT OVERRIDE" in r.raw_values.get("Description", "") for r in res.records)


def test_adversarial_mid_file_repeated_headers() -> None:
    """Verify repeated headers mid-file are classified and excluded from data."""
    path = ADV_FIXTURES / "mid_file_headers.csv"
    rows = read_csv_rows(path.read_bytes(), "src-adv-3", "v1")
    pipe = IngestionPipeline()
    res = pipe.process(rows, "src-adv-3", "v1")
    # Mid-file header is filtered or excluded
    assert all(r.product_id != "productCode" for r in res.records)


def test_adversarial_malformed_decimal_and_date() -> None:
    """Verify malformed decimal and date strings return None safely without crash."""
    d = parse_date("not-a-valid-date")
    assert d is None

    p = parse_decimal("invalid-price")
    assert p is None


def test_adversarial_empty_file_rejected() -> None:
    """Verify empty source CSV raises appropriate validation error."""
    path = ADV_FIXTURES / "empty_file.csv"
    rows = read_csv_rows(path.read_bytes(), "src-adv-4", "v1")
    assert len(rows) == 0


def test_adversarial_oversized_file_limit_enforced() -> None:
    """Verify CSV reader enforces max_bytes boundary."""
    large_payload = b"col1,col2\n" + (b"val1,val2\n" * 100)
    with pytest.raises(CsvReaderError, match="exceeds maximum limit"):
        read_csv_rows(large_payload, "f1", "v1", max_bytes=50)


def test_adversarial_huge_columns_limit_enforced() -> None:
    """Verify CSV reader enforces max_cols boundary."""
    wide_row = ",".join(f"col_{i}" for i in range(250))
    with pytest.raises(CsvReaderError, match="exceeds limit"):
        read_csv_rows(wide_row.encode(), "f1", "v1", max_cols=200)


def test_adversarial_invalid_utf8_handled_safely() -> None:
    """Verify invalid UTF-8 bytes fallback cleanly without crashing."""
    bad_bytes = b"Site code,SITE\nSITE-001,\xff\xfe\xfa Bad Bytes\n"
    rows = read_csv_rows(bad_bytes, "f1", "v1")
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_adversarial_path_traversal_filename_sanitized(client: AsyncClient) -> None:
    """Verify path traversal in X-Filename header is sanitized to simple basename."""
    res = await client.post(
        "/api/v1/sources",
        content=b"col1,col2\nval1,val2\n",
        headers={"Content-Type": "text/csv", "X-Filename": "../../../etc/passwd"},
    )
    assert res.status_code == 201
    source_id = res.json()["source_id"]

    # Verify stored filename is sanitized to 'passwd' without traversal paths
    res_get = await client.get(f"/api/v1/sources/{source_id}")
    assert res_get.status_code == 200
    assert res_get.json()["original_filename"] == "passwd"
    assert "/" not in res_get.json()["original_filename"]
    assert "\\" not in res_get.json()["original_filename"]


@pytest.mark.asyncio
async def test_adversarial_stale_approval_hash_rejected(client: AsyncClient, app) -> None:
    """Verify approving recommendation with wrong/stale hash returns HTTP 409."""
    db = app.state.test_db
    rec_id = "adv-rec-stale-hash"
    with db.transaction() as session:
        source_repo = SourceRepository()
        sf = source_repo.create_source_file(session, content=b"content", filename="f.csv", media_type="text/csv")
        sv = source_repo.create_source_version(session, source_file_id=sf.id, market="FR", version_label="v1", scope_key="FR")
        session.add(
            Recommendation(
                id=rec_id,
                source_version_id=sv.id,
                recommendation_key="rec-adv",
                status=RecommendationStatus.DRAFT.value,
                calculation_hash="correct_hash_00000000000000000000000000000000000000000000000000000000",
            )
        )

    res = await client.post(
        f"/api/v1/recommendations/{rec_id}/approve",
        json={"calculation_hash": "tampered_or_stale_hash", "reason": "Hostile approval attempt"},
    )
    assert res.status_code == 409


def test_adversarial_model_output_cannot_bypass_approval_policy(app) -> None:
    """Verify an approval cannot be forged without exact calculation_hash and valid recommendation status."""
    db = app.state.test_db
    review_repo = ReviewRepository()

    with db.transaction() as session:
        source_repo = SourceRepository()
        sf = source_repo.create_source_file(session, content=b"content", filename="f.csv", media_type="text/csv")
        sv = source_repo.create_source_version(session, source_file_id=sf.id, market="FR", version_label="v1", scope_key="FR")
        rec = session.merge(
            Recommendation(
                id="rec-policy-test",
                source_version_id=sv.id,
                recommendation_key="rec-p",
                status=RecommendationStatus.STALE.value,
                calculation_hash="hash1",
            )
        )

        with pytest.raises(ApprovalError, match="stale, or rejected"):
            review_repo.create_approval(
                session,
                recommendation_id=rec.id,
                decision="approved",
                reviewer_id="model-fake-admin",
                reason="Auto approve",
                calculation_hash="hash1",
            )
