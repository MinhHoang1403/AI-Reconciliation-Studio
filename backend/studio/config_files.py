"""Đọc các tệp cấu hình nghiệp vụ trong thư mục `config/` ở gốc dự án.

Những thứ hay phải chỉnh theo nghiệp vụ (cột chuẩn và tên cột hay gặp, loại bảng, từ điển,
ngưỡng và trọng số, các vòng khớp, chỉ dẫn và khuôn JSON gửi Gemini) nằm trong các tệp .json và
.md dễ đọc, không gán cứng trong code. Module này chỉ đọc và kiểm chúng:

- mỗi tệp được kiểm bằng một mô hình pydantic (đủ khóa, đúng kiểu, giá trị hợp lệ, tham chiếu
  chéo đúng: ví dụ cột bắt buộc của loại bảng phải là cột chuẩn có thật);
- sai ở đâu thì backend không khởi động và báo rõ tệp, khóa và lý do (ConfigError), thay vì
  chạy với cấu hình hỏng rồi cho kết quả sai âm thầm;
- đọc một lần lúc khởi động (lru_cache). Sửa tệp xong khởi động lại backend để áp dụng
  (xem config/README.md).

Thư mục mặc định là `config/` cạnh thư mục `backend/` (máy phát triển và trong container đều
đúng); đặt biến môi trường STUDIO_CONFIG_DIR để dùng thư mục khác.
"""

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

CONFIG_DIR = Path(
    os.environ.get("STUDIO_CONFIG_DIR") or Path(__file__).resolve().parents[2] / "config"
)

type FieldType = Literal["IDENTIFIER", "MONEY", "DATE", "PHONE", "TEXT", "CATEGORY"]


class ConfigError(RuntimeError):
    """Tệp cấu hình thiếu hoặc sai: thông điệp ghi rõ tệp, khóa và lý do."""


class _Strict(BaseModel):
    # Khóa lạ (gõ sai tên khóa) là lỗi, không lặng lẽ bỏ qua.
    model_config = ConfigDict(extra="forbid", frozen=True)


# ---------------------------------------------------------------- miền bán hàng


class FieldSpec(_Strict):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1)
    type: FieldType
    meaning: str = Field(min_length=1)
    aliases: tuple[str, ...]

    @field_validator("aliases")
    @classmethod
    def _plain_aliases(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        # Tên hay gặp được so sau khi tên cột đã bỏ dấu, chữ thường: viết sai dạng thì không
        # bao giờ khớp, nên báo ngay.
        for alias in value:
            if alias != alias.strip().lower() or not re.fullmatch(r"[a-z0-9 #]+", alias):
                raise ValueError(
                    f"tên hay gặp “{alias}” phải viết không dấu, chữ thường (ví dụ “ma don hang”)"
                )
        return value


class FieldsFile(_Strict):
    fields: tuple[FieldSpec, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique(self) -> "FieldsFile":
        keys = [field.key for field in self.fields]
        if len(keys) != len(set(keys)):
            raise ValueError("mã cột chuẩn bị trùng")
        return self


class KindDetect(_Strict):
    priority: int = Field(ge=1)
    any: tuple[str, ...] = ()
    all: tuple[str, ...] = ()


class TableKindSpec(_Strict):
    key: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    label: str = Field(min_length=1)
    family: str
    chain_order: int = Field(ge=0)
    detect: KindDetect
    required: tuple[tuple[str, ...], ...]
    key_field: str | None


class TableKindsFile(_Strict):
    unknown_label: str
    kinds: tuple[TableKindSpec, ...] = Field(min_length=1)


class VocabularyFile(_Strict):
    column_abbreviations: dict[str, str]
    row_number_column_names: tuple[str, ...]
    currency_words: tuple[str, ...] = Field(min_length=1)
    money_units: dict[str, int]
    honorifics: tuple[str, ...]
    cancelled_status_words: tuple[str, ...]
    transfer_noise_words: tuple[str, ...]
    masking_keep_words: tuple[str, ...]


# ---------------------------------------------------------------- ngưỡng, trọng số, các vòng


class MappingRules(_Strict):
    name_weight: float = Field(ge=0, le=1)
    value_weight: float = Field(ge=0, le=1)
    empty_column_value_score: float = Field(ge=0, le=1)
    min_name_score: float = Field(ge=0, le=1)
    weak_name_cap: float = Field(ge=0, le=1)
    type_compatibility: dict[FieldType, dict[str, float]]
    auto_apply_rule_score: float = Field(ge=0, le=1)
    auto_apply_rule_margin: float = Field(ge=0, le=1)
    auto_apply_combined_score: float = Field(ge=0, le=1)
    min_suggest_score: float = Field(ge=0, le=1)
    rule_weight_with_ai: float = Field(ge=0, le=1)
    ai_sample_values: int = Field(ge=0, le=20)

    @model_validator(mode="after")
    def _weights(self) -> "MappingRules":
        if abs(self.name_weight + self.value_weight - 1) > 1e-9:
            raise ValueError("name_weight + value_weight phải bằng 1")
        return self


class KeySelection(_Strict):
    weights: dict[Literal["match_rate", "fill", "unique"], float]
    min_match_rate: float = Field(ge=0, le=1)
    extract_codes_below_rate: float = Field(ge=0, le=1)
    group_when_unique_below: float = Field(ge=0, le=1)


class ScoreMatch(_Strict):
    weights: dict[Literal["date", "key", "name"], float]
    min_score: float = Field(ge=0, le=1)
    date_window_days: int = Field(ge=0, le=60)
    amount_tolerance: int = Field(ge=0)  # đồng; VND không có số lẻ


class GroupMatch(_Strict):
    max_rows: int = Field(ge=2, le=8)
    max_candidates: int = Field(ge=2, le=40)


class CodeExtraction(_Strict):
    min_precision: float = Field(ge=0, le=1)
    min_hits: int = Field(ge=1)


class Settlement(_Strict):
    business_days: int = Field(ge=0, le=30)
    min_late_share: float = Field(ge=0, le=1)


class Scope(_Strict):
    fields: tuple[str, ...]
    min_other_rate: float = Field(ge=0, le=1)
    max_own_rate: float = Field(ge=0, le=1)


class Chain(_Strict):
    min_pair_match_rate: float = Field(ge=0, le=1)
    min_pair_amount_rate: float = Field(ge=0, le=1)
    period_lead_days: int = Field(ge=0, le=60)


class RoundSpec(_Strict):
    round: str = Field(pattern=r"^[a-z_]+$")
    enabled: bool
    note: str = ""


class ReconciliationRules(_Strict):
    rounds: tuple[RoundSpec, ...] = Field(min_length=1)
    key_selection: KeySelection
    score_match: ScoreMatch
    group_match: GroupMatch
    code_extraction: CodeExtraction
    settlement: Settlement
    scope: Scope
    chain: Chain

    @model_validator(mode="after")
    def _rounds(self) -> "ReconciliationRules":
        names = [item.round for item in self.rounds]
        if len(names) != len(set(names)):
            raise ValueError("một vòng khớp được khai báo hai lần trong rounds")
        if not any(item.enabled for item in self.rounds):
            raise ValueError("cần bật ít nhất một vòng khớp trong rounds")
        return self


# ---------------------------------------------------------------- đọc tệp


def _read(relative: str) -> Any:
    path = CONFIG_DIR / relative
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise ConfigError(f"Thiếu tệp cấu hình {path}") from error
    if path.suffix != ".json":
        return text
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise ConfigError(
            f"{relative}: JSON sai cú pháp ở dòng {error.lineno}, cột {error.colno}: {error.msg}"
        ) from error


def _load[T: BaseModel](relative: str, model: type[T]) -> T:
    try:
        return model.model_validate(_read(relative))
    except ValidationError as error:
        problems = "; ".join(
            f"{'.'.join(map(str, item['loc'])) or '(cả tệp)'}: {item['msg']}"
            for item in error.errors()
        )
        raise ConfigError(f"{relative}: {problems}") from error


@lru_cache
def fields() -> FieldsFile:
    return _load("domains/sales/fields.json", FieldsFile)


@lru_cache
def table_kinds() -> TableKindsFile:
    loaded = _load("domains/sales/table-kinds.json", TableKindsFile)
    known = {field.key for field in fields().fields}
    for kind in loaded.kinds:
        used = {*kind.detect.any, *kind.detect.all, *(f for g in kind.required for f in g)}
        if kind.key_field:
            used.add(kind.key_field)
        unknown = sorted(used - known)
        if unknown:
            raise ConfigError(
                f"domains/sales/table-kinds.json: loại {kind.key} dùng cột chuẩn không có trong "
                f"fields.json: {', '.join(unknown)}"
            )
    return loaded


@lru_cache
def vocabulary() -> VocabularyFile:
    return _load("domains/sales/vocabulary.json", VocabularyFile)


@lru_cache
def mapping_rules() -> MappingRules:
    return _load("rules/mapping.json", MappingRules)


@lru_cache
def reconciliation_rules() -> ReconciliationRules:
    return _load("rules/reconciliation.json", ReconciliationRules)


_COMMENT = re.compile(r"\A\s*<!--.*?-->\s*\n", re.DOTALL)


@lru_cache
def prompt(name: str) -> str:
    """Chỉ dẫn gửi Gemini trong config/prompts/<name>.md (bỏ phần chú thích <!-- --> ở đầu)."""
    text = _COMMENT.sub("", _read(f"prompts/{name}.md"), count=1).strip()
    if not text:
        raise ConfigError(f"prompts/{name}.md: chỉ dẫn trống")
    return text


@lru_cache
def report_kind_meanings() -> dict[str, str]:
    data = _read("prompts/report-kind-meanings.json")
    meanings = data.get("meanings") if isinstance(data, dict) else None
    if not isinstance(meanings, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in meanings.items()
    ):
        raise ConfigError("prompts/report-kind-meanings.json: cần {\"meanings\": {loại: nghĩa}}")
    return dict(meanings)


def response_schema(name: str, **lists: list[str]) -> dict[str, Any]:
    """Khuôn JSON Gemini phải trả, trong config/schemas/<name>.json. Chỗ ghi "{tên}" (ví dụ
    "{field_keys_or_none}") được thay bằng danh sách code đưa vào, để danh sách mã cột chuẩn
    luôn lấy từ fields.json, không chép tay hai nơi."""
    schema = _read(f"schemas/{name}.json")
    if not isinstance(schema, dict):
        raise ConfigError(f"schemas/{name}.json: khuôn phải là một đối tượng JSON")

    def fill(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: fill(item) for key, item in value.items()}
        if isinstance(value, list):
            return [fill(item) for item in value]
        if isinstance(value, str) and re.fullmatch(r"\{[a-z_]+\}", value):
            key = value[1:-1]
            if key not in lists:
                raise ConfigError(f"schemas/{name}.json: không biết thay chỗ {value}")
            return list(lists[key])
        return value

    filled: dict[str, Any] = fill(schema)
    return filled


def check_all() -> None:
    """Đọc và kiểm mọi tệp (gọi lúc backend khởi động): sai ở đâu thì dừng và báo ngay."""
    fields()
    table_kinds()
    vocabulary()
    mapping_rules()
    reconciliation_rules()
    report_kind_meanings()
    for name in ("mapping", "cleaning-suggestion", "recon-explain", "report-comment", "assistant"):
        prompt(name)
