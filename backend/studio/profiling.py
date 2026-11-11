"""F05/F06: deterministic observations and review-only schema candidates [D]."""

import hashlib
import json
import re
import unicodedata

import polars as pl

from studio.contracts import ColumnProfile, DatasetProfile, SchemaDefinition, SourceColumn
from studio.contracts.api import PreparationColumn

PREPARATION_REVISION = "tabular-preparation-1"


def prepare_table(
    frame: pl.DataFrame, profile: DatasetProfile, *, extraction_warnings: bool
) -> tuple[pl.DataFrame, list[PreparationColumn]]:
    """Prepare a lexical snapshot with lossless ISO calendar dates where proven.

    Input is the complete parsed table and its profile. Physical row locators,
    identifiers, empty strings and unknown semantics remain unchanged. Mixed or
    invalid date columns stay lexical and retain their original values.
    """
    casts = []
    findings = []
    summary = []
    for column in profile.columns:
        data_type = "string"
        invalid_dates = 0
        if "date_candidate" in column.type_candidates and not column.identifier_candidate:
            values = frame[column.column_id]
            iso_mask = values.str.contains(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
            nonempty = len(values) - column.null_count - column.empty_count
            if iso_mask.sum() == nonempty:
                source = pl.col(column.column_id)
                parsed_date = pl.when(~source.str.starts_with("0000")).then(
                    source.str.strptime(pl.Date, "%Y-%m-%d", strict=False)
                )
                converted = frame.select(parsed_date.alias(column.column_id)).to_series()
                round_trip = (converted.dt.strftime("%Y-%m-%d") == values).sum()
                invalid_dates = nonempty - int(round_trip)
                if invalid_dates:
                    findings.append(
                        pl.when(
                            source.is_not_null()
                            & (source != "")
                            & (parsed_date.dt.strftime("%Y-%m-%d") != source).fill_null(True)
                        ).then(pl.lit(f"INVALID_DATE:{column.column_id}"))
                    )
                if not (invalid_dates or column.empty_count or extraction_warnings):
                    casts.append(converted)
                    data_type = "date"
        summary.append(
            PreparationColumn(
                column_id=column.column_id,
                data_type=data_type,
                null_count=column.null_count,
                empty_count=column.empty_count,
                duplicate_count=column.duplicate_count,
                invalid_date_count=invalid_dates,
            )
        )
    flags = (
        pl.concat_list(findings).list.drop_nulls() if findings else pl.lit([], pl.List(pl.String))
    )
    return frame.with_columns(casts).with_columns(flags.alias("_preparation_flags")), summary


def normalized_name(value: str) -> str:
    value = value.lower().replace("đ", "d")
    return "".join(c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c))


def profile_table(
    frame: pl.DataFrame,
    columns: list[SourceColumn],
    table_id: str,
    workspace_id: str,
    artifact_id: str,
) -> DatasetProfile:
    """F05: exact counts, capped representative values; no inferred monetary locale.

    O(rows × columns), with at most 5 samples per column. Samples stay scoped; AI
    receives redacted structural samples from build_evidence_context instead.
    """
    profiles = []
    key_candidates = []
    for col in columns:
        values = frame[col.id]
        nonnull = values.drop_nulls()
        distinct = nonnull.n_unique()
        nonempty = [str(v) for v in nonnull.to_list() if v != ""]
        candidates = ["string"]
        if nonempty and all(re.fullmatch(r"[+-]?\d+(?:[.,]\d+)?", v) for v in nonempty):
            candidates.append("numeric_candidate")
        if nonempty and all(re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", v) for v in nonempty):
            candidates.append("date_candidate")
        identifier = any(re.fullmatch(r"0\d+", v) for v in nonempty) or bool(
            re.search(
                r"(?:^|[^a-z0-9])(?:id|ma|reference|code)(?:$|[^a-z0-9])", normalized_name(col.name)
            )
        )
        if identifier:
            candidates.append("identifier")
        if distinct == frame.height and frame.height > 0 and values.null_count() == 0:
            key_candidates.append([col.id])
        observed = values.unique(maintain_order=True).head(3).to_list()
        if nonempty:
            for edge in (min(nonempty, key=len), max(nonempty, key=len)):
                if edge not in observed:
                    observed.append(edge)
        lengths = [len(v) for v in nonempty]
        profiles.append(
            ColumnProfile(
                column_id=col.id,
                name=col.name,
                null_count=values.null_count(),
                empty_count=(values == "").sum(),
                distinct_count=distinct,
                duplicate_count=len(nonnull) - distinct,
                type_candidates=candidates,
                min_value=min(nonempty) if nonempty else None,
                max_value=max(nonempty) if nonempty else None,
                min_length=min(lengths) if lengths else None,
                max_length=max(lengths) if lengths else None,
                samples=observed[:5],
                evidence_ids=[f"{table_id}:{col.id}"],
                identifier_candidate=identifier,
                observations=column_observations(nonempty),
            )
        )
    return DatasetProfile(
        source_table_id=table_id,
        workspace_id=workspace_id,
        artifact_id=artifact_id,
        row_count=frame.height,
        columns=profiles,
        key_candidates=key_candidates,
    )


ALIASES = {
    "reference_id": {"ma don", "order id", "order_id", "tracking id", "ma van don"},
    "gross_amount": {"gross amount", "gross", "tong truoc giam"},
    "net_amount": {"net amount", "net"},
    "description": {"description", "mo ta", "ten"},
    "event_date": {"event date", "ngay phat sinh"},
    "currency": {"currency", "tien te"},
    "shop_id": {"shop", "shop id", "cua hang"},
    "platform": {"platform", "san"},
}

# [D] A small bilingual role vocabulary, applied only to column-name proposals.
# Longest phrases win before individual words: money basis and document roles
# remain distinct. This never rewrites raw IDs, source signatures or approvals.
FIELD_TERMS = {
    "ma tien te": "currency",
    "don vi tien te": "currency",
    "don vi tien": "currency",
    "loai tien": "currency",
    "tien te": "currency",
    "dong tien": "currency",
    "truoc giam tru": "gross",
    "truoc khau tru": "gross",
    "truoc phi": "gross",
    "sau giam tru": "net",
    "sau khau tru": "net",
    "sau phi": "net",
    "thuc nhan": "net amount",
    "gia tri gop": "gross amount",
    "tien gop": "gross amount",
    "da thanh toan": "paid",
    "da chi tra": "paid",
    "da tra": "paid",
    "phai thu": "receivable",
    "phai tra": "payable",
    "du kien": "expected",
    "don hang": "order",
    "don mua": "order",
    "khach hang": "customer",
    "nguoi mua": "customer",
    "khach mua": "customer",
    "nha cung cap": "supplier",
    "hoa don": "invoice",
    "phieu thu": "receipt",
    "bien lai thu": "receipt",
    "van don": "tracking",
    "thanh toan": "payment",
    "chi tra": "payment",
    "tra tien": "payment",
    "nhan tien": "receipt",
    "thu tien": "receipt",
    "quyet toan": "settlement",
    "doi soat": "settlement",
    "ngan hang": "bank",
    "tham chieu": "reference",
    "giao dich": "transaction",
    "dieu chinh": "adjustment",
    "hoan tien": "refund",
    "hoan lai": "refund",
    "hoan tra": "refund",
    "ban hang": "sale",
    "tra hang": "return",
    "hang tra": "return",
    "san pham": "sku",
    "hang hoa": "sku",
    "ma hang": "sku id",
    "so luong": "quantity",
    "gia von": "unit cost",
    "don gia": "unit cost",
    "gia tri ton kho": "inventory value",
    "gia tri hang ton": "inventory value",
    "chot ton": "snapshot",
    "chup ton": "snapshot",
    "ton kho": "inventory",
    "den han": "due",
    "dao han": "due",
    "phat sinh": "event",
    "thoi diem": "date",
    "so tien": "amount",
    "gia tri": "amount",
    "khoan": "amount",
    "cong no": "amount",
    "ma so": "id",
    "so hoa don": "invoice id",
    "so phieu thu": "receipt id",
    "ma": "id",
    "ngay": "date",
    "tien": "amount",
    "phi": "fee",
    "lo": "batch",
    "kho": "warehouse",
    "goc": "original",
    "mo ta": "description",
    "code": "id",
    "identifier": "id",
    "number": "id",
}
FIELD_PATTERN = re.compile(
    r"\b(?:"
    + "|".join(
        re.escape(phrase)
        for phrase in sorted(FIELD_TERMS, key=lambda phrase: (-len(phrase.split()), -len(phrase)))
    )
    + r")\b"
)


def field_name_tokens(value: str) -> tuple[str, ...]:
    """Bilingual lexical concepts for suggestions; not a semantic equivalence proof.

    NFKD/accent folding is shared with the profiler. Phrase boundaries prevent
    substring translation, and unrecognized qualifiers remain for abstention.
    """
    value = re.sub(r"([a-z])([A-Z])", r"\1 \2", value)
    name = " ".join(re.findall(r"[a-z0-9]+", normalized_name(value)))
    translated = FIELD_PATTERN.sub(lambda match: FIELD_TERMS[match[0]], name)
    return tuple(translated.split())


def find_mapping_candidates(
    profile: DatasetProfile, schema: SchemaDefinition
) -> dict[str, list[str]]:
    """F06: exact aliases, then unique compatible token containment for review.

    [D] name/instance/constraint approach inspired by Rahm–Bernstein taxonomy.
    O(source fields × target fields); generic labels never supply business roles.
    """

    money_roles = {
        "gross",
        "net",
        "fee",
        "paid",
        "expected",
        "receivable",
        "payable",
        "refund",
        "return",
        "adjustment",
    }

    def concepts(tokens: tuple[str, ...]) -> frozenset[str]:
        words = set(tokens)
        if "currency" in words:
            words -= {"id", "loai"}
        # "Phí" sau từ chỉ cơ sở là một điều kiện của chỉ tiêu, không phải
        # chính chỉ tiêu. Chỉ dùng khi tên cột có tín hiệu là giá trị tiền.
        if "amount" in words:
            qualifiers = [word for word in tokens if word not in {"cac", "nhung", "amount"}]
            for direction, qualified in zip(qualifiers, qualifiers[1:], strict=False):
                if qualified == "fee" and direction in {"truoc", "sau"}:
                    words.discard("fee")
                    words.add("gross" if direction == "truoc" else "net")
        if words & money_roles:
            words.discard("amount")
        return frozenset(words)

    target_names = {
        field.id: {
            concepts(field_name_tokens(value))
            for value in {field.id, field.name} | ALIASES.get(field.id, set())
        }
        for field in schema.fields
    }
    output: dict[str, list[str]] = {}
    for source in profile.columns:
        name = field_name_tokens(source.name)
        words = set(name)
        # Negation, alternatives and explicit uncertainty are not a role assertion.
        if (
            words & {"khong", "chua", "hoac", "hay", "not", "or", "unknown"}
            or {"gross", "net"} <= words
        ):
            output[source.column_id] = []
            continue
        compatible = [
            f
            for f in schema.fields
            if not (source.identifier_candidate and f.data_type == "decimal")
        ]
        semantic = concepts(name)
        if {"gross", "net"} <= semantic:
            output[source.column_id] = []
            continue
        short_roles = money_roles | {"currency", "quantity"}
        if "amount" not in words:
            short_roles -= {"refund", "return", "adjustment"}
        targets = [f.id for f in compatible if semantic in target_names[f.id]]
        if not targets and name and set(name) not in ({"amount"}, {"total"}, {"date"}, {"code"}):
            partial = [
                f.id
                for f in compatible
                if (
                    f.data_type == "string"
                    or f.data_type == "date"
                    and source.observations.get("date_formats")
                    or f.data_type == "decimal"
                    and source.observations.get("numeric_locales")
                )
                and not (
                    semantic
                    & {"gross", "net", "fee", "refund", "quantity", "receivable", "payable"}
                    - set().union(*target_names[f.id])
                )
                and any(
                    (len(alias) >= 2 or bool(alias & short_roles)) and alias < semantic
                    for alias in target_names[f.id]
                )
            ]
            targets = partial if len(partial) == 1 else []
        output[source.column_id] = targets[:5]
    return output


def source_signature(profile: DatasetProfile) -> str:
    payload = [
        (c.column_id, c.name, c.type_candidates, c.identifier_candidate) for c in profile.columns
    ]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()


def default_schema(workspace_id: str, schema_id: str) -> SchemaDefinition:
    from studio.contracts import SchemaField

    names = [
        ("reference_id", "Mã tham chiếu", "string"),
        ("description", "Mô tả", "string"),
        ("gross_amount", "Tiền trước giảm trừ", "decimal"),
        ("net_amount", "Tiền sau giảm trừ", "decimal"),
        ("amount", "Số tiền cần định nghĩa", "decimal"),
        ("currency", "Tiền tệ", "string"),
        ("event_date", "Ngày phát sinh", "date"),
        ("shop_id", "Cửa hàng", "string"),
        ("platform", "Nền tảng", "string"),
    ]
    return SchemaDefinition(
        id=schema_id,
        workspace_id=workspace_id,
        name="Dữ liệu giao dịch tổng quát",
        revision=1,
        entity_kind="unknown",
        grain="unknown",
        fields=[
            SchemaField.model_validate({"id": i, "name": n, "data_type": t}) for i, n, t in names
        ],
    )


def column_observations(values: list[str]) -> dict[str, int | str | list[str] | dict[str, int]]:
    """[D] Thống kê toàn cột, không thay bằng chứng ngữ nghĩa.

    Giá trị gốc chỉ dùng local; không suy tiền tệ từ đa số.
    """
    from collections import Counter
    from datetime import datetime

    from studio.errors import DomainError
    from studio.normalization import parse_decimal

    date_counts: dict[str, int] = {}
    formats = {
        r"\d{4}-\d{2}-\d{2}": ["%Y-%m-%d"],
        r"\d{2}/\d{2}/\d{4}": ["%d/%m/%Y", "%m/%d/%Y"],
        r"\d{4}-\d{2}-\d{2}[ T].+": [
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
        ],
    }
    for pattern, candidates in formats.items():
        subset = [v for v in values if re.fullmatch(pattern, v)]
        for fmt in candidates:
            count = 0
            for v in subset:
                try:
                    datetime.strptime(v, fmt)
                    count += 1
                except ValueError:
                    pass
            if count:
                date_counts[fmt] = count
    numeric: dict[str, int] = {}
    negative = zero = 0
    for locale in ("en-US", "vi-VN"):
        count = 0
        for value in values:
            if not re.fullmatch(r"[+\-\d.,]+", value):
                continue
            try:
                number = parse_decimal(value, locale)
                count += 1
                if locale == "en-US" and number is not None:
                    negative += number < 0
                    zero += number == 0
            except DomainError:
                pass
        numeric[locale] = count
    return dict(
        nonempty_count=len(values),
        leading_zero_count=sum(bool(re.fullmatch(r"0\d+", v)) for v in values),
        date_formats=date_counts,
        numeric_locales=numeric,
        negative_en_us=negative,
        zero_en_us=zero,
        currency_counts=dict(
            Counter(
                v
                for v in values
                if v
                in {
                    "VND",
                    "USD",
                    "EUR",
                    "GBP",
                    "JPY",
                    "CNY",
                    "KRW",
                    "SGD",
                    "THB",
                    "AUD",
                    "CAD",
                    "CHF",
                    "HKD",
                }
            )
        ),
    )
