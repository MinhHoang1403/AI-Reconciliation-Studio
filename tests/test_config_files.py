"""Kiểm thư mục config/: mọi tệp đọc được, tệp sai báo đúng chỗ, các vòng khớp bật/tắt được.

Cấu hình nghiệp vụ (cột chuẩn, loại bảng, từ điển, ngưỡng, các vòng khớp, chỉ dẫn và khuôn JSON
gửi Gemini) nằm trong config/; code chỉ đọc. Sửa sai một tệp thì backend phải dừng và nói rõ
sai ở đâu, không chạy tiếp với cấu hình hỏng.
"""

import json
import shutil
from collections.abc import Callable, Iterator
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from studio import config_files, matching_rounds
from studio.reading import ROW_REF
from studio.recon_verification import verify
from studio.reconciliation import ReconConfig, Side, reconcile, summarize
from studio.sales_fields import FIELDS_BY_KEY, TABLE_KIND_LABELS, infer_table_kind

LOADERS = (
    config_files.fields,
    config_files.table_kinds,
    config_files.vocabulary,
    config_files.mapping_rules,
    config_files.reconciliation_rules,
    config_files.prompt,
    config_files.report_kind_meanings,
)


@pytest.fixture
def config_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Bản sao config/ để sửa thử; đọc lại từ bản sao, xong thì trả về như cũ."""
    copy = tmp_path / "config"
    shutil.copytree(config_files.CONFIG_DIR, copy)
    monkeypatch.setattr(config_files, "CONFIG_DIR", copy)
    for loader in LOADERS:
        loader.cache_clear()
    yield copy
    for loader in LOADERS:
        loader.cache_clear()


def edit(copy: Path, relative: str, change: Callable[[Any], object]) -> None:
    path = copy / relative
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_every_config_file_loads_and_matches_the_code() -> None:
    config_files.check_all()
    matching_rounds.check_configured_rounds()
    assert len(FIELDS_BY_KEY) == 17 and "order_id" in FIELDS_BY_KEY
    assert list(TABLE_KIND_LABELS)[-1] == "UNKNOWN"
    assert infer_table_kind({"order_id", "fee", "net_amount"}) == "ORDERS_PLATFORM"
    assert infer_table_kind({"debit", "order_id"}) == "BANK_STATEMENT"
    assert infer_table_kind({"amount"}) == "UNKNOWN"
    schema = config_files.response_schema(
        "mapping-response", table_kinds=["A"], field_keys_or_none=["x", "NONE"]
    )
    assert schema["properties"]["table_kind"]["enum"] == ["A"]
    assert "<!--" not in config_files.prompt("assistant")


def test_a_wrong_value_names_the_file_and_the_key(config_copy: Path) -> None:
    edit(config_copy, "rules/mapping.json", lambda data: data.update(name_weight=0.9))
    with pytest.raises(config_files.ConfigError, match=r"rules/mapping.json: .*name_weight"):
        config_files.mapping_rules()


def test_a_typo_in_a_key_is_refused(config_copy: Path) -> None:
    edit(config_copy, "rules/reconciliation.json",
         lambda data: data["score_match"].update(min_scor=0.5))
    with pytest.raises(config_files.ConfigError, match="min_scor"):
        config_files.reconciliation_rules()


def test_broken_json_reports_line_and_column(config_copy: Path) -> None:
    broken = config_copy / "domains/sales/vocabulary.json"
    broken.write_text('{"honorifics": [', encoding="utf-8")
    with pytest.raises(config_files.ConfigError, match="JSON sai cú pháp ở dòng 1"):
        config_files.vocabulary()


def test_aliases_must_be_written_without_accents(config_copy: Path) -> None:
    edit(config_copy, "domains/sales/fields.json",
         lambda data: data["fields"][0]["aliases"].append("Mã đơn"))
    with pytest.raises(config_files.ConfigError, match="không dấu"):
        config_files.fields()


def test_table_kind_cannot_use_an_unknown_field(config_copy: Path) -> None:
    edit(config_copy, "domains/sales/table-kinds.json",
         lambda data: data["kinds"][0]["required"].append(["so_luong"]))
    with pytest.raises(config_files.ConfigError, match="so_luong"):
        config_files.table_kinds()


def test_unknown_matching_round_is_refused(config_copy: Path) -> None:
    edit(config_copy, "rules/reconciliation.json",
         lambda data: data["rounds"].append({"round": "ai_guess", "enabled": True}))
    with pytest.raises(config_files.ConfigError, match="ai_guess"):
        matching_rounds.check_configured_rounds()


def test_turning_rounds_off_changes_results_but_keeps_them_verifiable(config_copy: Path) -> None:
    """Chỉ bật vòng khớp theo mã: cặp cùng mã vẫn khớp, hai đơn trả gộp (không mã) không còn được
    ghép nhóm mà thành "chỉ có ở một bên"; kết quả vẫn qua kiểm chứng (mỗi dòng đúng một kết quả,
    tiền mỗi bên được bảo toàn)."""
    schema: dict[str, Any] = {
        ROW_REF: pl.Int64, "order_id": pl.String, "amount": pl.Decimal(20, 2), "day": pl.Date
    }
    day = date(2026, 10, 1)
    left = pl.DataFrame(
        {ROW_REF: [2, 3, 4], "order_id": ["HD1", None, None],
         "amount": [Decimal(100), Decimal(300), Decimal(700)], "day": [day] * 3},
        schema=schema,
    )
    right = pl.DataFrame(
        {ROW_REF: [2, 3], "order_id": ["HD1", None],
         "amount": [Decimal(100), Decimal(1000)], "day": [day] * 2},
        schema=schema,
    )
    config = ReconConfig("order_id", "order_id", "amount", "amount", "day", "day")

    def kinds() -> list[str]:
        results = reconcile(Side(left), Side(right), config)
        report = verify(
            left, right, [asdict(item) for item in results], config.to_json(), summarize(results)
        )
        assert report["passed"], report
        return sorted(item.kind for item in results)

    assert kinds() == ["MANY_TO_ONE", "MATCHED"]
    edit(config_copy, "rules/reconciliation.json", lambda data: data.update(rounds=[
        {"round": "key_match", "enabled": True},
        {"round": "score_match", "enabled": False},
        {"round": "group_match", "enabled": False},
    ]))
    config_files.reconciliation_rules.cache_clear()
    assert kinds() == ["MATCHED", "ONLY_IN_A", "ONLY_IN_A", "ONLY_IN_B"]
