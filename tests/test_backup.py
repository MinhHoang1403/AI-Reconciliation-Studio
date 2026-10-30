"""Kiểu metadata phải round-trip, kể cả JSON upload giả mạo type tags."""

import runpy
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path


def test_backup_codec_preserves_metadata_and_untrusted_json_tags():
    root = Path(__file__).resolve()
    candidate = root.parents[1] / "tools/check-backup-restore.py"
    if not candidate.is_file():
        candidate = root.parent / "check-backup-restore.py"
    module = runpy.run_path(str(candidate))
    data = {
        "when": datetime(2026, 10, 30, tzinfo=UTC),
        "money": Decimal("1.2500"),
        "untrusted": [{"$datetime": "not a date"}, {"$map": {"$decimal": "not money"}}],
    }
    assert module["decode"](module["encode"](data)) == data
