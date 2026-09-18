"""Ingestion service coordinating parsing, idempotency, and database persistence."""

import json
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import EventStatus, SourceStatus
from app.ingestion.contracts import IngestionResult
from app.ingestion.csv_reader import read_csv_rows
from app.ingestion.matrix_reader import read_matrix_rows
from app.ingestion.pipeline import IngestionPipeline
from app.ingestion.xlsx_reader import read_xlsx_rows
from app.persistence import EventRepository, SourceRepository, sha256_bytes, sha256_payload
from app.schemas.ingestion import IngestionResponse


class IngestionService:
    """Orchestrates source parsing, event tracking, and transactional persistence."""

    def __init__(
        self,
        source_repo: SourceRepository | None = None,
        event_repo: EventRepository | None = None,
        pipeline: IngestionPipeline | None = None,
    ) -> None:
        self.sources = source_repo or SourceRepository()
        self.events = event_repo or EventRepository()
        self.pipeline = pipeline or IngestionPipeline()

    def ingest_csv(
        self,
        session: Session,
        *,
        content: bytes,
        filename: str = "FR-v2--Sheet1.csv",
        event_key: str | None = None,
        tenant_id: str | None = None,
        source_system: str = "france_procurement_upload",
    ) -> IngestionResponse:
        """Process and persist a CSV source file."""
        content_hash = sha256_bytes(content)
        actual_event_key = event_key or f"evt:ingest:csv:{content_hash}"

        event_result = self.events.create_or_get_event(
            session,
            event_key=actual_event_key,
            payload_hash=content_hash,
            event_type="source_ingestion_csv",
            tenant_id=tenant_id,
        )

        if event_result.replayed:
            # Replay existing result
            existing_source = self.sources.find_source_by_hash(session, content_hash, tenant_id=tenant_id)
            if existing_source and existing_source.versions:
                v = existing_source.versions[-1]
                rec_count = len(v.records)
                meta = v.metadata_json or {}
                return IngestionResponse(
                    source_file_id=existing_source.id,
                    source_version_id=v.id,
                    status=v.status,
                    market=v.market,
                    update_mode=v.update_mode,
                    supplier_scope=meta.get("supplier_scope", []),
                    total_rows=meta.get("total_rows", rec_count),
                    record_count=rec_count,
                    valid_count=meta.get("valid_count", rec_count),
                    review_count=meta.get("review_count", 0),
                    result_hash=meta.get("result_hash", content_hash),
                    replayed=True,
                )

        # 1. Persist or retrieve SourceFile
        source_file = self.sources.find_source_by_hash(session, content_hash, tenant_id=tenant_id)
        if not source_file:
            source_file = self.sources.create_source_file(
                session,
                content=content,
                filename=filename,
                media_type="text/csv",
                source_system=source_system,
                tenant_id=tenant_id,
                metadata={"sha256": content_hash},
                synthetic=True,
            )

        temp_version_id = f"ver-{content_hash[:8]}"

        # 2. Extract rows and run pipeline
        raw_rows = read_csv_rows(
            content=content,
            source_file_id=source_file.id,
            source_version_id=temp_version_id,
        )

        ingestion_result: IngestionResult = self.pipeline.process(
            raw_rows=raw_rows,
            source_file_id=source_file.id,
            source_version_id=temp_version_id,
        )

        # 3. Create SourceVersion
        valid_records = [r for r in ingestion_result.records if r.validation_status == "valid"]
        version_status = (
            SourceStatus.ACCEPTED.value
            if not ingestion_result.review_items
            else SourceStatus.NEEDS_REVIEW.value
        )

        source_version = self.sources.create_source_version(
            session,
            source_file_id=source_file.id,
            tenant_id=tenant_id,
            market=ingestion_result.scope.market,
            version_label=filename,
            update_mode=ingestion_result.scope.update_mode,
            scope_key=f"{ingestion_result.scope.market}:{','.join(ingestion_result.scope.supplier_scope)}",
            status=version_status,
            metadata_json={
                "parser_name": ingestion_result.parser_name,
                "parser_version": ingestion_result.parser_version,
                "rules_version": ingestion_result.rules_version,
                "result_hash": ingestion_result.result_hash,
                "supplier_scope": ingestion_result.scope.supplier_scope,
                "total_rows": ingestion_result.total_rows,
                "valid_count": len(valid_records),
                "review_count": len(ingestion_result.review_items),
                "review_items": [item.model_dump() for item in ingestion_result.review_items],
            },
        )

        # 4. Insert records
        record_dicts: list[dict[str, Any]] = []
        for r in ingestion_result.records:
            record_dicts.append({
                "record_key": r.source_record_key,
                "source_row_number": r.source_row_number,
                "source_sheet": r.sheet_name,
                "raw_values_json": r.raw_values,
                "supplier": r.supplier_id,
                "product": r.product_id,
                "record_date": str(r.transaction_date) if r.transaction_date else None,
                "quantity": str(r.quantity) if r.quantity is not None else None,
                "unit": r.unit,
                "currency": r.currency,
                "value": str(r.signed_value) if r.signed_value is not None else None,
                "record_kind": r.record_kind,
                "validation_status": r.validation_status,
                "validation_errors_json": r.errors,
            })

        self.sources.insert_source_records(session, source_version.id, record_dicts)

        # 5. Complete event
        event_result.event.status = EventStatus.COMPLETED.value
        event_result.event.source_file_id = source_file.id
        event_result.event.source_version_id = source_version.id

        return IngestionResponse(
            source_file_id=source_file.id,
            source_version_id=source_version.id,
            status=source_version.status,
            market=source_version.market,
            update_mode=source_version.update_mode,
            supplier_scope=ingestion_result.scope.supplier_scope,
            total_rows=ingestion_result.total_rows,
            record_count=len(ingestion_result.records),
            valid_count=len(valid_records),
            review_count=len(ingestion_result.review_items),
            result_hash=ingestion_result.result_hash,
            replayed=False,
        )

    def ingest_xlsx(
        self,
        session: Session,
        *,
        content: bytes,
        filename: str = "source.xlsx",
        event_key: str | None = None,
        tenant_id: str | None = None,
        source_system: str = "procurement_xlsx_upload",
        max_bytes: int | None = None,
    ) -> IngestionResponse:
        """Process a bounded XLSX upload using the shared ingestion pipeline."""
        content_hash = sha256_bytes(content)
        actual_event_key = event_key or f"evt:ingest:xlsx:{content_hash}"
        event_result = self.events.create_or_get_event(
            session,
            event_key=actual_event_key,
            payload_hash=content_hash,
            event_type="source_ingestion_xlsx",
            tenant_id=tenant_id,
        )
        existing_source = self.sources.find_source_by_hash(session, content_hash, tenant_id=tenant_id)
        if event_result.replayed and existing_source and existing_source.versions:
            version = existing_source.versions[-1]
            meta = version.metadata_json or {}
            return IngestionResponse(
                source_file_id=existing_source.id,
                source_version_id=version.id,
                status=version.status,
                market=version.market,
                update_mode=version.update_mode,
                supplier_scope=meta.get("supplier_scope", []),
                total_rows=meta.get("total_rows", len(version.records)),
                record_count=len(version.records),
                valid_count=meta.get("valid_count", len(version.records)),
                review_count=meta.get("review_count", 0),
                result_hash=meta.get("result_hash", content_hash),
                replayed=True,
            )
        if existing_source is None:
            existing_source = self.sources.create_source_file(
                session,
                content=content,
                filename=filename,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                source_system=source_system,
                tenant_id=tenant_id,
                metadata={"sha256": content_hash},
                synthetic=False,
            )

        temp_version_id = f"ver-{content_hash[:8]}"
        raw_rows = read_xlsx_rows(
            content=content,
            source_file_id=existing_source.id,
            source_version_id=temp_version_id,
            **({"max_bytes": max_bytes} if max_bytes is not None else {}),
        )
        ingestion_result = self.pipeline.process(
            raw_rows=raw_rows,
            source_file_id=existing_source.id,
            source_version_id=temp_version_id,
        )
        valid_records = [r for r in ingestion_result.records if r.validation_status == "valid"]
        version_status = SourceStatus.ACCEPTED.value if not ingestion_result.review_items else SourceStatus.NEEDS_REVIEW.value
        source_version = self.sources.create_source_version(
            session,
            source_file_id=existing_source.id,
            tenant_id=tenant_id,
            market=ingestion_result.scope.market,
            version_label=filename,
            update_mode=ingestion_result.scope.update_mode,
            scope_key=f"{ingestion_result.scope.market}:{','.join(ingestion_result.scope.supplier_scope)}",
            status=version_status,
            metadata_json={
                "parser_name": ingestion_result.parser_name,
                "parser_version": ingestion_result.parser_version,
                "rules_version": ingestion_result.rules_version,
                "result_hash": ingestion_result.result_hash,
                "supplier_scope": ingestion_result.scope.supplier_scope,
                "total_rows": ingestion_result.total_rows,
                "valid_count": len(valid_records),
                "review_count": len(ingestion_result.review_items),
                "review_items": [item.model_dump() for item in ingestion_result.review_items],
            },
        )
        self.sources.insert_source_records(session, source_version.id, [
            {
                "record_key": r.source_record_key,
                "source_row_number": r.source_row_number,
                "source_sheet": r.sheet_name,
                "raw_values_json": r.raw_values,
                "supplier": r.supplier_id,
                "product": r.product_id,
                "record_date": str(r.transaction_date) if r.transaction_date else None,
                "quantity": str(r.quantity) if r.quantity is not None else None,
                "unit": r.unit,
                "currency": r.currency,
                "value": str(r.signed_value) if r.signed_value is not None else None,
                "record_kind": r.record_kind,
                "validation_status": r.validation_status,
                "validation_errors_json": r.errors,
            }
            for r in ingestion_result.records
        ])
        event_result.event.status = EventStatus.COMPLETED.value
        event_result.event.source_file_id = existing_source.id
        event_result.event.source_version_id = source_version.id
        return IngestionResponse(
            source_file_id=existing_source.id,
            source_version_id=source_version.id,
            status=source_version.status,
            market=source_version.market,
            update_mode=source_version.update_mode,
            supplier_scope=ingestion_result.scope.supplier_scope,
            total_rows=ingestion_result.total_rows,
            record_count=len(ingestion_result.records),
            valid_count=len(valid_records),
            review_count=len(ingestion_result.review_items),
            result_hash=ingestion_result.result_hash,
            replayed=False,
        )

    def ingest_matrix(
        self,
        session: Session,
        *,
        matrix: list[list[Any]],
        filename: str = "FR-v2.json",
        event_key: str | None = None,
        tenant_id: str | None = None,
        source_system: str = "france_procurement_matrix",
    ) -> IngestionResponse:
        """Process and persist a raw matrix source payload."""
        matrix_bytes = json.dumps(matrix, sort_keys=True, separators=(",", ":")).encode("utf-8")
        payload_hash = sha256_payload(matrix)
        actual_event_key = event_key or f"evt:ingest:matrix:{payload_hash}"

        event_result = self.events.create_or_get_event(
            session,
            event_key=actual_event_key,
            payload_hash=payload_hash,
            event_type="source_ingestion_matrix",
            tenant_id=tenant_id,
        )

        if event_result.replayed:
            existing_source = self.sources.find_source_by_hash(session, payload_hash, tenant_id=tenant_id)
            if existing_source and existing_source.versions:
                v = existing_source.versions[-1]
                rec_count = len(v.records)
                meta = v.metadata_json or {}
                return IngestionResponse(
                    source_file_id=existing_source.id,
                    source_version_id=v.id,
                    status=v.status,
                    market=v.market,
                    update_mode=v.update_mode,
                    supplier_scope=meta.get("supplier_scope", []),
                    total_rows=meta.get("total_rows", rec_count),
                    record_count=rec_count,
                    valid_count=meta.get("valid_count", rec_count),
                    review_count=meta.get("review_count", 0),
                    result_hash=meta.get("result_hash", payload_hash),
                    replayed=True,
                )

        source_file = self.sources.find_source_by_hash(session, payload_hash, tenant_id=tenant_id)
        if not source_file:
            source_file = self.sources.create_source_file(
                session,
                content=matrix_bytes,
                filename=filename,
                media_type="application/json",
                source_system=source_system,
                tenant_id=tenant_id,
                metadata={"payload_hash": payload_hash},
                synthetic=True,
            )

        temp_version_id = f"ver-{payload_hash[:8]}"

        raw_rows = read_matrix_rows(
            matrix=matrix,
            source_file_id=source_file.id,
            source_version_id=temp_version_id,
        )

        ingestion_result: IngestionResult = self.pipeline.process(
            raw_rows=raw_rows,
            source_file_id=source_file.id,
            source_version_id=temp_version_id,
        )

        valid_records = [r for r in ingestion_result.records if r.validation_status == "valid"]
        version_status = (
            SourceStatus.ACCEPTED.value
            if not ingestion_result.review_items
            else SourceStatus.NEEDS_REVIEW.value
        )

        source_version = self.sources.create_source_version(
            session,
            source_file_id=source_file.id,
            tenant_id=tenant_id,
            market=ingestion_result.scope.market,
            version_label=filename,
            update_mode=ingestion_result.scope.update_mode,
            scope_key=f"{ingestion_result.scope.market}:{','.join(ingestion_result.scope.supplier_scope)}",
            status=version_status,
            metadata_json={
                "parser_name": ingestion_result.parser_name,
                "parser_version": ingestion_result.parser_version,
                "rules_version": ingestion_result.rules_version,
                "result_hash": ingestion_result.result_hash,
                "supplier_scope": ingestion_result.scope.supplier_scope,
                "total_rows": ingestion_result.total_rows,
                "valid_count": len(valid_records),
                "review_count": len(ingestion_result.review_items),
                "review_items": [item.model_dump() for item in ingestion_result.review_items],
            },
        )

        record_dicts: list[dict[str, Any]] = []
        for r in ingestion_result.records:
            record_dicts.append({
                "record_key": r.source_record_key,
                "source_row_number": r.source_row_number,
                "source_sheet": r.sheet_name,
                "raw_values_json": r.raw_values,
                "supplier": r.supplier_id,
                "product": r.product_id,
                "record_date": str(r.transaction_date) if r.transaction_date else None,
                "quantity": str(r.quantity) if r.quantity is not None else None,
                "unit": r.unit,
                "currency": r.currency,
                "value": str(r.signed_value) if r.signed_value is not None else None,
                "record_kind": r.record_kind,
                "validation_status": r.validation_status,
                "validation_errors_json": r.errors,
            })

        self.sources.insert_source_records(session, source_version.id, record_dicts)

        event_result.event.status = EventStatus.COMPLETED.value
        event_result.event.source_file_id = source_file.id
        event_result.event.source_version_id = source_version.id

        return IngestionResponse(
            source_file_id=source_file.id,
            source_version_id=source_version.id,
            status=source_version.status,
            market=source_version.market,
            update_mode=source_version.update_mode,
            supplier_scope=ingestion_result.scope.supplier_scope,
            total_rows=ingestion_result.total_rows,
            record_count=len(ingestion_result.records),
            valid_count=len(valid_records),
            review_count=len(ingestion_result.review_items),
            result_hash=ingestion_result.result_hash,
            replayed=False,
        )
