"""Snapshot/verify application metadata and artifact bytes across restart/recreate.

Run inside the existing backend container. The snapshot stays on the artifact volume;
no raw values, keys or database connection strings are printed or committed.
"""

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import select
from studio.config import settings
from studio.database import (
    ArtifactRow,
    AttemptRow,
    AuditRow,
    CanonicalRow,
    DatasetRow,
    JobRow,
    MappingRow,
    ProjectRow,
    SchemaRow,
    SessionFactory,
    TableRow,
    TraceRow,
    VersionRow,
    WorkspaceRow,
)
from studio.storage import checksum, storage_path


def capture() -> dict[str, Any]:
    result: dict[str, Any] = {}
    with SessionFactory() as db:
        active = db.scalar(
            select(JobRow.id)
            .where(JobRow.status.in_(["QUEUED", "RUNNING", "RETRYABLE_FAILURE"]))
            .limit(1)
        )
        if active:
            raise SystemExit("BLOCKED: wait for active jobs before persistence snapshot")
        for model in (
            WorkspaceRow,
            ProjectRow,
            DatasetRow,
            VersionRow,
            TableRow,
            SchemaRow,
            MappingRow,
            CanonicalRow,
            JobRow,
            AttemptRow,
            AuditRow,
            TraceRow,
        ):
            records = []
            for row in db.scalars(select(model)):
                values = {c.name: getattr(row, c.name) for c in model.__table__.columns}
                records.append(
                    {
                        "id": row.id,
                        "metadata_sha256": hashlib.sha256(
                            json.dumps(values, sort_keys=True, default=str).encode()
                        ).hexdigest(),
                    }
                )
            result[model.__tablename__] = sorted(records, key=lambda r: r["id"])
        artifacts = []
        for row in db.scalars(select(ArtifactRow)):
            actual = checksum(storage_path(settings.storage_root, row.storage_key))
            if actual != row.sha256:
                raise SystemExit("FAIL: artifact checksum differs from published ref")
            artifacts.append({"id": row.id, "kind": row.kind, "sha256": actual})
        result["artifacts"] = sorted(artifacts, key=lambda r: r["id"])
    return result


def main() -> None:
    snapshot: Path = settings.storage_root / "verification" / "persistence.json"
    actual = capture()
    if sys.argv[1:] == ["snapshot"]:
        snapshot.parent.mkdir(exist_ok=True)
        snapshot.write_text(json.dumps(actual, sort_keys=True), encoding="utf-8")
        print("Snapshot captured:", {k: len(v) for k, v in actual.items()})
    elif sys.argv[1:] == ["verify"]:
        if json.loads(snapshot.read_text(encoding="utf-8")) != actual:
            raise SystemExit("FAIL: metadata or artifact bytes changed after restart/recreate")
        print(
            "PASS persistence: metadata, approvals, canonical refs and all artifact bytes unchanged"
        )
    else:
        raise SystemExit("Use snapshot or verify")


if __name__ == "__main__":
    main()
