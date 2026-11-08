"""Kiểu metadata phải round-trip, kể cả JSON upload giả mạo type tags."""

import json
import runpy
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import Column, MetaData, String, Table


def backup_module():
    root = Path(__file__).resolve()
    candidate = root.parents[1] / "tools/check-backup-restore.py"
    if not candidate.is_file():
        candidate = root.parent / "check-backup-restore.py"
    return runpy.run_path(str(candidate))


def test_backup_codec_preserves_metadata_and_untrusted_json_tags():
    module = backup_module()
    data = {
        "when": datetime(2026, 10, 30, tzinfo=UTC),
        "money": Decimal("1.2500"),
        "untrusted": [{"$datetime": "not a date"}, {"$map": {"$decimal": "not money"}}],
    }
    assert module["decode"](module["encode"](data)) == data


def test_streamed_backup_preserves_exact_existing_format(tmp_path):
    module = backup_module()
    rows = {
        "nguồn": [{"id": "0001", "money": Decimal("-1.2500"), "raw": {"$map": []}}],
        "empty": [],
        "dates": [{"at": datetime(2026, 11, 6, tzinfo=UTC), "null": None}],
    }
    target = tmp_path / "metadata.json"
    offsets = module["write_metadata"](target, rows)
    assert target.read_bytes() == module["canonical"](rows).encode("utf-8")
    with target.open("rb") as stream:
        for table, ranges in offsets.items():
            restored = []
            for start, length in ranges:
                stream.seek(start)
                restored.append(module["decode"](json.loads(stream.read(length))))
            assert restored == rows[table]


@pytest.mark.parametrize(
    "actual", [[{"id": "changed"}], [], [{"id": "a"}, {"id": "b"}], [{"id": "a"}, {"id": "a"}]]
)
def test_backup_metadata_comparison_rejects_changed_missing_and_extra_rows(actual):
    module = backup_module()
    metadata = MetaData()
    Table("records", metadata, Column("id", String, primary_key=True))

    class Connection:
        def execute(self, statement):
            return self

        def mappings(self):
            return actual

    with pytest.raises(RuntimeError, match="Backup metadata differs: records"):
        module["verify_metadata"](Connection(), metadata, {"records": [{"id": "a"}]})
