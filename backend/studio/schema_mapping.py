"""F08–F10: validate proposals, approvals and typed transformation plans."""

from dataclasses import dataclass

from studio.contracts import (
    ArithmeticTransform,
    CoalesceTransform,
    DatasetProfile,
    EnumTransform,
    MappingRevision,
    MappingStatus,
    SchemaDefinition,
    SchemaProposal,
)
from studio.errors import DomainError
from studio.profiling import normalized_name


def validate_mapping(
    proposal: SchemaProposal,
    profile: DatasetProfile,
    schema: SchemaDefinition,
    for_approval: bool = False,
) -> SchemaProposal:
    """F08/F27: verify real IDs/evidence, cardinality, type and monetary semantics.

    Valid AI JSON cannot self-approve. Unknown/ambiguous decisions remain for review.
    Caller separately authorizes approver; this pure validator never writes data.
    """
    fields = {f.id: f for f in schema.fields}
    sources = {c.column_id: c for c in profile.columns}
    seen_sources: set[str] = set()
    seen_targets: set[str] = set()
    for decision in proposal.decisions:
        if decision.source_field not in sources or decision.source_field in seen_sources:
            raise DomainError("INVALID_SOURCE_FIELD", "Cột nguồn không tồn tại hoặc bị ánh xạ lặp.")
        seen_sources.add(decision.source_field)
        source = sources[decision.source_field]
        if not set(decision.evidence_ids) <= set(source.evidence_ids):
            raise DomainError("INVALID_EVIDENCE", "Bằng chứng không thuộc cột nguồn.")
        if not for_approval and decision.decision in {
            MappingStatus.APPROVED,
            MappingStatus.SUPERSEDED,
            MappingStatus.REJECTED,
        }:
            raise DomainError("AI_CANNOT_APPROVE", "AI không có quyền phê duyệt ánh xạ.")
        target_id = decision.candidate_target
        if target_id is None:
            continue
        if target_id not in fields or target_id in seen_targets:
            raise DomainError("INVALID_TARGET_FIELD", "Trường đích không tồn tại hoặc bị lặp.")
        seen_targets.add(target_id)
        field = fields[target_id]
        op = decision.transformation_candidate.op
        if field.data_type == "decimal" and op not in {
            "parse_decimal",
            "add_fields",
            "subtract_fields",
            "aggregate_by",
        }:
            raise DomainError(
                "TRANSFORM_TYPE_MISMATCH", "Trường số tiền cần phép chuyển đổi Decimal."
            )
        if field.data_type == "date" and op != "parse_date":
            raise DomainError("TRANSFORM_TYPE_MISMATCH", "Trường ngày cần định dạng và múi giờ.")
        if field.data_type == "string" and op not in {
            "cast_string_preserve",
            "trim_if_approved",
            "coalesce_with_rule",
        }:
            raise DomainError("TRANSFORM_TYPE_MISMATCH", "Phép biến đổi không phù hợp kiểu chuỗi.")
        if field.data_type == "enum" and op != "normalize_enum":
            raise DomainError(
                "TRANSFORM_TYPE_MISMATCH", "Kiểu danh mục cần bảng giá trị được duyệt."
            )
        if field.data_type == "decimal":
            ambiguous = normalized_name(source.name).strip() in {
                "total",
                "tong",
                "amount",
                "so tien",
            }
            if not for_approval and (
                ambiguous or not field.semantic_metric or not field.amount_basis
            ):
                decision.decision = MappingStatus.AMBIGUOUS
                decision.unresolved_questions = ["Xác nhận định nghĩa số tiền, đơn vị và tiền tệ."]
            if for_approval and not all(
                value
                and value.strip().casefold()
                not in {"", "unknown", "ambiguous", "n/a", "none", "needs_review"}
                for value in (field.semantic_metric, field.amount_basis, field.currency, field.unit)
            ):
                raise DomainError(
                    "MONETARY_SEMANTICS_REQUIRED",
                    "Cần xác nhận định nghĩa, cơ sở, đơn vị và tiền tệ của số tiền.",
                )
        if source.identifier_candidate and field.data_type == "decimal":
            raise DomainError(
                "IDENTIFIER_CAST_BLOCKED", "Không chuyển cột định danh thành số tiền."
            )
        if for_approval and decision.decision != MappingStatus.APPROVED:
            raise DomainError("MAPPING_NOT_APPROVED", "Từng trường sử dụng phải được xác nhận.")
        if for_approval and decision.grain_assumption != schema.grain:
            raise DomainError("GRAIN_ASSUMPTION_MISMATCH", "Grain của ánh xạ khác schema đã duyệt.")
    if for_approval:
        if (
            not seen_targets
            or schema.grain.strip().casefold() in {"unknown", "ambiguous", ""}
            or schema.entity_kind.strip().casefold() in {"unknown", "ambiguous", ""}
        ):
            raise DomainError(
                "GRAIN_REVIEW_REQUIRED", "Cần xác nhận loại dữ liệu và ý nghĩa mỗi dòng."
            )
        if any(f.required and f.id not in seen_targets for f in schema.fields):
            raise DomainError("REQUIRED_FIELD_MISSING", "Thiếu ánh xạ trường bắt buộc.")
    return proposal


@dataclass(frozen=True)
class TransformPlan:
    mapping: MappingRevision
    schema: SchemaDefinition


def compile_transform_plan(
    mapping: MappingRevision, schema: SchemaDefinition, profile: DatasetProfile
) -> TransformPlan:
    """F10: compile only approved typed AST with scoped, approved rule references."""
    if mapping.status != MappingStatus.APPROVED or not mapping.approved_by:
        raise DomainError("MAPPING_NOT_APPROVED", "Ánh xạ chưa được phê duyệt.")
    if mapping.schema_id != schema.id or mapping.schema_revision != schema.revision:
        raise DomainError("SCHEMA_REVISION_MISMATCH", "Phiên bản schema không tương thích.")
    proposal = SchemaProposal(
        entity_kind=schema.entity_kind,
        grain=schema.grain,
        status="PROPOSED",
        decisions=mapping.decisions,
    )
    validate_mapping(proposal, profile, schema, for_approval=True)
    sources = {c.column_id for c in profile.columns}
    rules = {r.id: r for r in mapping.rules}
    for decision in mapping.decisions:
        transform = decision.transformation_candidate
        rule_id = getattr(transform, "rule_id", getattr(transform, "mapping_id", None))
        if rule_id:
            rule = rules.get(rule_id)
            if rule is None or rule.operation != transform.op or not rule.approved_by:
                raise DomainError("TRANSFORM_RULE_UNAPPROVED", "Quy tắc biến đổi chưa được duyệt.")
            if not set(rule.evidence_ids) <= {e for c in profile.columns for e in c.evidence_ids}:
                raise DomainError("INVALID_EVIDENCE", "Bằng chứng quy tắc không hợp lệ.")
            if isinstance(transform, (ArithmeticTransform, CoalesceTransform)):
                if not set(transform.fields) <= sources or transform.fields != rule.fields:
                    raise DomainError("TRANSFORM_RULE_FIELDS", "Đầu vào quy tắc không khớp.")
            if isinstance(transform, ArithmeticTransform):
                target = next(f for f in schema.fields if f.id == decision.candidate_target)
                if (
                    rule.metric != target.semantic_metric
                    or rule.currency != target.currency
                    or rule.unit != target.unit
                ):
                    raise DomainError(
                        "ARITHMETIC_SEMANTICS_REQUIRED",
                        "Phép tính cần metric, đơn vị và tiền tệ đã duyệt.",
                    )
            if isinstance(transform, EnumTransform) and rule.fields != [decision.source_field]:
                raise DomainError(
                    "TRANSFORM_RULE_FIELDS", "Quy tắc danh mục không thuộc cột nguồn."
                )
            if isinstance(transform, EnumTransform) and not rule.enum_values:
                raise DomainError("ENUM_RULE_EMPTY", "Bảng chuyển đổi danh mục chưa có giá trị.")
        if transform.op == "aggregate_by":
            field = next(f for f in schema.fields if f.id == decision.candidate_target)
            rule = rules[transform.rule_id]
            if rule.fields != [decision.source_field]:
                raise DomainError("TRANSFORM_RULE_FIELDS", "Quy tắc nhóm không thuộc cột nguồn.")
            if (
                transform.metric != field.semantic_metric
                or rule.metric != field.semantic_metric
                or rule.currency != field.currency
                or rule.unit != field.unit
                or rule.grain != schema.grain
                or set(transform.keys) != set(schema.business_key_fields)
                or not set(transform.keys) <= {d.candidate_target for d in mapping.decisions}
            ):
                raise DomainError(
                    "AGGREGATE_SEMANTICS_REQUIRED",
                    "Nhóm cần khóa, grain, metric và tiền tệ đã duyệt.",
                )
    return TransformPlan(mapping, schema)
