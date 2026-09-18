"""Tests for evidence, corrections, and record lineage API endpoints."""

import pytest
from httpx import AsyncClient

from app.db.models import (
    EvidenceLink,
    Recommendation,
    RecommendationStatus,
    SourceFile,
    SourceRecord,
    SourceVersion,
)


def _setup_evidence_and_records(app) -> tuple[str, str, str, str]:
    db = app.state.test_db
    with db.transaction() as session:
        src_file = SourceFile(
            original_filename="spend-evidence.csv",
            media_type="text/csv",
            size_bytes=250,
            sha256="ev_sha_456",
        )
        session.add(src_file)
        session.flush()

        ver = SourceVersion(
            source_file_id=src_file.id,
            market="FR",
            version_label="v1",
            update_mode="initial",
            scope_key="FR",
        )
        session.add(ver)
        session.flush()

        src_rec = SourceRecord(
            source_version_id=ver.id,
            record_key="TXN-0001",
            source_row_number=5,
            raw_values_json={"Item": "TXN-0001", "Price": "15.00"},
            supplier="sup-novex",
            product="WLF-1001",
            currency="EUR",
            value="15.00",
            record_kind="line",
            validation_status="valid",
        )
        session.add(src_rec)
        session.flush()

        rec = Recommendation(
            source_version_id=ver.id,
            recommendation_key="rec-ev-1",
            status=RecommendationStatus.DRAFT.value,
            facts_json={"price": "15.00"},
            explanation_json={},
            calculation_hash="ev_calc_hash_999",
            result_hash="ev_calc_hash_999",
        )
        session.add(rec)
        session.flush()

        link = EvidenceLink(
            recommendation_id=rec.id,
            source_record_id=src_rec.id,
            source_file_id=src_file.id,
            relation="primary_basis",
        )
        session.add(link)
        session.flush()

        return rec.id, src_rec.id, link.id, src_file.id


@pytest.mark.asyncio
async def test_evidence_detail_and_grouped_list(client: AsyncClient, app) -> None:
    rec_id, src_rec_id, link_id, file_id = _setup_evidence_and_records(app)

    # Get evidence detail
    ev_res = await client.get(f"/api/v1/evidence/{link_id}")
    assert ev_res.status_code == 200
    ev_data = ev_res.json()
    assert ev_data["id"] == link_id
    assert ev_data["recommendation_id"] == rec_id
    assert ev_data["source_record_id"] == src_rec_id
    assert ev_data["source_file_id"] == file_id
    assert ev_data["relation"] == "primary_basis"

    # List evidence for recommendation
    grouped_res = await client.get(f"/api/v1/recommendations/{rec_id}/evidence")
    assert grouped_res.status_code == 200
    links = grouped_res.json()
    assert len(links) == 1
    assert links[0]["id"] == link_id


@pytest.mark.asyncio
async def test_record_lineage(client: AsyncClient, app) -> None:
    _, src_rec_id, _, _ = _setup_evidence_and_records(app)

    lineage_res = await client.get(f"/api/v1/records/{src_rec_id}/lineage")
    assert lineage_res.status_code == 200
    lineage = lineage_res.json()
    assert lineage["record_id"] == src_rec_id
    assert lineage["record_key"] == "TXN-0001"
    assert lineage["source_row_number"] == 5
    assert lineage["lineage"] == "source_initial"


@pytest.mark.asyncio
async def test_submit_correction_and_detail(client: AsyncClient, app) -> None:
    rec_id, src_rec_id, _, _ = _setup_evidence_and_records(app)

    # Submit correction for unit_price
    corr_res = await client.post(
        f"/api/v1/recommendations/{rec_id}/corrections",
        json={
            "source_record_id": src_rec_id,
            "field_name": "unit_price",
            "original_value": "15.00",
            "corrected_value": "12.50",
            "reason": "Reviewer confirmed discount tariff",
        },
    )
    assert corr_res.status_code == 201
    corr_data = corr_res.json()
    corr_id = corr_data["id"]
    assert corr_data["source_record_id"] == src_rec_id
    assert corr_data["field_name"] == "unit_price"
    assert corr_data["corrected_value"] == "12.50"

    # Verify recommendation transitioned to needs_review
    rec_res = await client.get(f"/api/v1/recommendations/{rec_id}")
    assert rec_res.json()["status"] == "needs_review"

    # Get correction detail
    get_corr_res = await client.get(f"/api/v1/corrections/{corr_id}")
    assert get_corr_res.status_code == 200
    assert get_corr_res.json()["id"] == corr_id


@pytest.mark.asyncio
async def test_submit_correction_invalid_field(client: AsyncClient, app) -> None:
    rec_id, src_rec_id, _, _ = _setup_evidence_and_records(app)

    res = await client.post(
        f"/api/v1/recommendations/{rec_id}/corrections",
        json={
            "source_record_id": src_rec_id,
            "field_name": "disallowed_field_xyz",
            "corrected_value": "test",
            "reason": "Invalid field change",
        },
    )
    assert res.status_code == 400
    assert res.json()["code"] == "invalid_request"
