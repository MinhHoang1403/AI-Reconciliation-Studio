"""Đo độ chính xác ánh xạ cột trên hai bộ có đáp án.

- Bộ mẫu (tests/fixtures/sales/*.csv, *.xlsx + anh-xa-dung.csv): tên cột quen thuộc.
- Bộ tên cột mới (tests/fixtures/sales/ten-cot-moi.json): tên cột chưa dùng khi soạn quy tắc.

Mặc định chỉ dùng quy tắc (không tốn phí). Thêm `--with-ai` để gọi Gemini thật cho mỗi bảng
(cần GEMINI_API_KEY; mỗi bảng một lần gọi, có trace Langfuse nếu đã cấu hình).

Cách chạy:  uv run --locked python tools/evaluate_mapping.py [--with-ai]
"""

import argparse
import csv
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from studio import reading  # noqa: E402
from studio.mapping_rules import score_columns  # noqa: E402
from studio.mapping_service import (  # noqa: E402
    SYSTEM_INSTRUCTION,
    build_ai_payload,
    decide,
    parse_ai_reply,
    response_schema,
)
from studio.models import DatasetTable  # noqa: E402
from studio.profiling import TableProfile, profile_table  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "sales"
SAMPLE_FILES = [
    "don-hang-san-tmdt.xlsx",
    "don-hang-cua-hang.csv",
    "giao-dich-cong-thanh-toan.csv",
    "sao-ke-ngan-hang.xlsx",
]


@dataclass
class Case:
    """Một bảng cần ánh xạ cùng đáp án {tên cột: mã cột chuẩn hoặc None}."""

    label: str
    profile: TableProfile
    truth: dict[str, str | None]


@dataclass
class Score:
    total: int = 0
    correct: int = 0
    auto: int = 0
    auto_correct: int = 0
    errors: list[str] = field(default_factory=list)

    def report(self, title: str) -> str:
        accuracy = self.correct / self.total if self.total else 0
        auto_share = self.auto / self.total if self.total else 0
        auto_precision = self.auto_correct / self.auto if self.auto else 0
        lines = [
            f"{title}: đúng {self.correct}/{self.total} cột ({accuracy:.0%}); "
            f"tự áp dụng {self.auto}/{self.total} ({auto_share:.0%}), "
            f"trong đó đúng {self.auto_correct}/{self.auto} ({auto_precision:.0%})",
        ]
        lines += [f"  - {error}" for error in self.errors]
        return "\n".join(lines)


def sample_cases() -> list[Case]:
    truth: dict[tuple[str, str], dict[str, str | None]] = {}
    with (FIXTURES / "anh-xa-dung.csv").open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            truth.setdefault((row["file"], row["sheet"]), {})[row["column"]] = row["field"] or None
    cases = []
    for name in SAMPLE_FILES:
        content = (FIXTURES / name).read_bytes()
        raws = [reading.read_csv(content)] if name.endswith(".csv") else reading.read_xlsx(content)
        for raw in raws:
            table = reading.build_table(raw, reading.detect_header_row(raw.frame))
            key = (name, raw.name or "")
            if key in truth:
                cases.append(
                    Case(f"{name} {raw.name or ''}".strip(), profile_table(table.frame), truth[key])
                )
    return cases


def unseen_cases() -> list[Case]:
    data = json.loads((FIXTURES / "ten-cot-moi.json").read_text(encoding="utf-8"))
    cases = []
    for table in data["tables"]:
        frame = pl.DataFrame(
            {
                column["name"]: [value or None for value in column["values"]]
                for column in table["columns"]
            }
        )
        frame = frame.with_row_index(reading.ROW_REF, offset=2)
        cases.append(
            Case(
                table["name"],
                profile_table(frame),
                {column["name"]: column["field"] or None for column in table["columns"]},
            )
        )
    return cases


def evaluate(cases: list[Case], with_ai: bool) -> Score:
    from studio.gemini_client import AiUnavailable, generate_json

    score = Score()
    for case in cases:
        names = [column.name for column in case.profile.columns]
        scores = score_columns(case.profile)
        ai = None
        if with_ai:
            payload = build_ai_payload(DatasetTable(sheet_name=None), case.profile, scores)
            try:
                reply = generate_json(
                    purpose="danh-gia-anh-xa-cot",
                    system_instruction=SYSTEM_INSTRUCTION,
                    payload=payload,
                    response_schema=response_schema(),
                )
                ai = parse_ai_reply(reply.data, names)[1]
            except AiUnavailable as error:
                score.errors.append(f"{case.label}: không gọi được Gemini ({error.message})")
        for decision in decide(scores, ai, names):
            expected = case.truth[decision["column_name"]]
            correct = decision["field_key"] == expected
            score.total += 1
            score.correct += correct
            if decision["status"] == "AUTO":
                score.auto += 1
                score.auto_correct += correct
            if not correct:
                score.errors.append(
                    f"{case.label} / {decision['column_name']}: chọn "
                    f"{decision['field_key']} ({decision['status']}), đúng là {expected}"
                )
    return score


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-ai", action="store_true", help="gọi Gemini thật (tốn phí)")
    args = parser.parse_args()
    mode = "quy tắc + Gemini" if args.with_ai else "chỉ quy tắc"
    print(evaluate(sample_cases(), args.with_ai).report(f"Bộ mẫu ({mode})"))
    print(evaluate(unseen_cases(), args.with_ai).report(f"Bộ tên cột mới ({mode})"))


if __name__ == "__main__":
    main()
