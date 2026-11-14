"""Seed isolated browser fixtures from previously verified synthetic cache bytes.

Prepare the bundle on the host, then load it in the running TEST backend.
Neither mode invokes or reserves a request with the document provider.
"""

import argparse
import hashlib
import json
import runpy
from pathlib import Path
from typing import Any
from uuid import uuid4


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(backup: Path, previous: Path, bundle: Path) -> None:
    decode = runpy.run_path(Path(__file__).with_name("check-backup-restore.py"))["decode"]
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["restore_status"] == "PASS"
    metadata = backup / "metadata.json"
    assert digest(metadata) == manifest["metadata_sha256"]
    rows = decode(json.loads(metadata.read_text(encoding="utf-8")))
    receipt = json.loads(previous.read_text(encoding="utf-8"))
    project_id = receipt["project_id"]
    assert any(
        row["resource_id"] == project_id and row["action"] == "PROJECT_CLASSIFIED_TEST"
        for row in rows["audit_events"]
    )
    assert receipt["integration"] == "PASS"
    bundle.mkdir(parents=True, exist_ok=True)
    documents = {}
    for suffix in ("pdf", "docx"):
        recorded = receipt[suffix]
        dataset = next(row for row in rows["datasets"] if row["id"] == recorded["dataset_id"])
        assert dataset["project_id"] == project_id
        assert dataset["name"] == f"synthetic-transactions.{suffix}"
        parsed = next(row for row in rows["artifacts"] if row["id"] == recorded["artifact_id"])
        version = next(
            row for row in rows["dataset_versions"] if row["id"] == parsed["dataset_version_id"]
        )
        assert version["dataset_id"] == dataset["id"]
        raw = next(
            row
            for row in rows["artifacts"]
            if row["dataset_version_id"] == version["id"] and row["kind"] == "raw"
        )
        assert raw["sha256"] == dataset["sha256"] == recorded["sha256"]
        for artifact in (raw, parsed):
            path = (backup / "files" / artifact["storage_key"]).resolve()
            assert path.is_relative_to((backup / "files").resolve())
            assert digest(path) == artifact["sha256"] == manifest["files"][artifact["storage_key"]]
            (bundle / f"{suffix}-{artifact['kind']}").write_bytes(path.read_bytes())
        documents[suffix] = dict(dataset=dataset, version=version, raw=raw, parsed=parsed)
    (bundle / "bundle.json").write_text(
        json.dumps({"backup_id": manifest["backup_id"], "documents": documents}, default=str),
        encoding="utf-8",
    )


def seed(bundle: Path) -> dict[str, Any]:
    from sqlalchemy import text
    from studio.config import settings
    from studio.database import (
        ArtifactRow,
        AuditRow,
        DatasetRow,
        ProjectRow,
        SessionFactory,
        VersionRow,
    )
    from studio.document_parser import DocumentExtraction
    from studio.storage import storage_path

    payload = json.loads((bundle / "bundle.json").read_text(encoding="utf-8"))
    project_id = str(uuid4())
    receipt: dict[str, Any] = dict(
        project_id=project_id, backup_id=payload["backup_id"], documents={}
    )
    with SessionFactory() as db:
        schema = db.scalar(text("SELECT current_schema()"))
        assert schema and schema.startswith("test_") and settings.storage_root.name == schema
        assert not settings.allow_cloud_parsing
        db.add(
            ProjectRow(
                id=project_id,
                workspace_id="demo",
                name="TEST PDF/DOCX cache",
                business_scope="synthetic cached document acceptance",
            )
        )
        db.flush()
        db.add(
            AuditRow(
                workspace_id="demo",
                actor_id="demo-owner",
                action="PROJECT_CLASSIFIED_TEST",
                resource_id=project_id,
            )
        )
        for suffix, record in payload["documents"].items():
            dataset, version, raw, parsed = (
                record[name] for name in ("dataset", "version", "raw", "parsed")
            )
            dataset_id, version_id, raw_id, parsed_id = (str(uuid4()) for _ in range(4))
            db.add(
                DatasetRow(
                    id=dataset_id,
                    workspace_id="demo",
                    project_id=project_id,
                    owner_id="demo-owner",
                    name=dataset["name"],
                    sha256=dataset["sha256"],
                    parse_signature=dataset["parse_signature"],
                    status="PARSED",
                )
            )
            db.flush()
            db.add(
                VersionRow(
                    id=version_id,
                    dataset_id=dataset_id,
                    revision=version["revision"],
                    parser_revision=version["parser_revision"],
                    parse_config=version["parse_config"],
                )
            )
            db.flush()
            for artifact_id, artifact in ((raw_id, raw), (parsed_id, parsed)):
                kind = artifact["kind"]
                content = bundle / f"{suffix}-{kind}"
                assert digest(content) == artifact["sha256"]
                if kind == "document":
                    extraction = DocumentExtraction.model_validate_json(content.read_bytes())
                    assert [page.page_number for page in extraction.pages] == [1]
                key = f"demo/{version_id}/{kind}/{artifact_id}"
                target = storage_path(settings.storage_root, key)
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as stream:
                    stream.write(content.read_bytes())
                metadata = artifact["metadata_json"]
                if kind == "document":
                    metadata["source_file"]["id"] = raw_id
                db.add(
                    ArtifactRow(
                        id=artifact_id,
                        workspace_id="demo",
                        dataset_version_id=version_id,
                        kind=kind,
                        sha256=artifact["sha256"],
                        revision=artifact["revision"],
                        quality=artifact["quality"],
                        storage_key=key,
                        metadata_json=metadata,
                    )
                )
            receipt["documents"][suffix] = dict(
                dataset_id=dataset_id,
                artifact_id=parsed_id,
                raw_sha256=raw["sha256"],
                parsed_sha256=parsed["sha256"],
                original_artifact_id=parsed["id"],
            )
        db.commit()
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--previous", type=Path)
    args = parser.parse_args()
    if args.backup and args.previous:
        prepare(args.backup, args.previous, args.bundle)
    elif not (args.backup or args.previous):
        print(json.dumps(seed(args.bundle)))
    else:
        parser.error("Provide both --backup and --previous to prepare a bundle")
