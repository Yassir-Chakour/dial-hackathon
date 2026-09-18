from app.config import Settings
from app.db.models import SourceStatus
from app.db.session import create_database
from app.reconciliation.versioning import select_current_version
from app.persistence import SourceService


def test_current_version_selection_rejects_ambiguous_accepted_versions(tmp_path) -> None:
    database = create_database(Settings(app_env="test", database_url=f"sqlite:///{tmp_path / 'versions.db'}"))
    database.create_schema()
    try:
        source = SourceService()
        with database.transaction() as session:
            first, _, _ = source.accept_version(session, content=b"a", filename="a.csv", media_type="text/csv",
                                                market="FR", version_label="v1", scope_key="FR:supplier",
                                                event_key="source-a", payload={})
            second, _, _ = source.accept_version(session, content=b"b", filename="b.csv", media_type="text/csv",
                                                 market="FR", version_label="v2", scope_key="FR:supplier",
                                                 event_key="source-b", payload={})
            selection = select_current_version(session, market="FR", scope_key="FR:supplier")
            assert selection.version is None
            assert selection.issues[0].code == "multiple_current_versions"
            first.status = SourceStatus.SUPERSEDED.value
            selection = select_current_version(session, market="FR", scope_key="FR:supplier")
            assert selection.version is not None and selection.version.id == second.id
    finally:
        database.dispose()

