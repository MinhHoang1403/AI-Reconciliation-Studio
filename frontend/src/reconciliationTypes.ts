import type { Canonical, Profile, Schema } from "./types";

export type Pair = {left: string; right: string};
export type Slot = {canonical_id:string;role:string;date_field:string;time_basis:string;currency_field:string|null;
  filters:Record<string,string>;coverage_start:string;coverage_end:string;completeness:string;snapshot_at:string;settlement_due_at:string|null};
export type Metric = Pair & {metric_id:string;currency:string;unit:string;amount_basis:string;sign_convention:"SOURCE_SIGNED";
  absolute_tolerance:string;relative_tolerance:string|null;rounding_scale:number|null;rounding_mode:string};
export type Plan = {name:string;entity_kind:string;left:Slot;right:Slot;join_keys:Pair[];comparison_metrics:Metric[];attributes:Pair[];
  comparison_grain:string;cardinality:string;aggregation:string;period_start:string;period_end:string;timezone:string;
  effective_from:string;effective_to:string|null;allow_partial:boolean;duplicate_policy:"REVIEW";fuzzy_fields:Pair[];
  fuzzy_block_keys:Pair[];fuzzy_min_score:number;fuzzy_top_k:number;evidence_ids:string[]};
export type Catalogue = {project_id:string;name:string;canonical:Canonical;schema_definition:Schema;identifier_fields:string[];profile:Profile};
export type Proposal = {id:string;origin:string;contract_id:string|null;proposal:{status:string;plan:Plan|null;missing_requirements:string[];reasoning:string}};
export type Rate = {numerator:number;denominator:number;percent:string|null};
export type Snapshot = {id:string;run_id:string;comparison_unit:string;eligible_definition:string;eligible_units:number;period_start:string;period_end:string;
  timezone:string;full_match_rate:Rate;linkage_rate:Rate;exception_rate:Rate;automation_coverage:Rate;review_rate:Rate;
  monetary:{metric_id:string;currency:string;unit:string;comparable_groups:number;signed_variance:string;absolute_variance:string}[];
  linkage_counts:Record<string,number>;comparison_counts:Record<string,number>;excluded_counts:Record<string,number>;unresolved_cases_at_run:number};
export type Run = {id:string;status:string;contract_id:string;checks:{name:string;passed:boolean;details:string}[];metric_snapshot:Snapshot|null};
export type Group = {id:string;key:(string|null)[];linkage_state:string;comparison_state:string;exception_types:string[];
  members:{side:string;record_id:string;canonical_id:string;evidence:{file_id:string;source_table_id:string;sheet:string;row:number}[]}[];
  comparisons:{metric_id:string;currency:string;left_amount:string|null;right_amount:string|null;delta:string|null;absolute_variance:string|null}[];
  candidates:{left_record_id:string;right_record_id:string;score:number;status:string}[]};
export type Case = {id:string;match_group_id:string;type:string;workflow_state:string;notes:string;severity_basis:string};
export const reconciliationLabels:Record<string,string> = {
  VERIFIED:"Đã xác minh",PARTIAL_VERIFIED:"Đã xác minh một phần",VERIFICATION_FAILED:"Kiểm chứng thất bại",DRAFT:"Chờ chạy",RUNNING:"Đang chạy",
  LINKED:"Đã liên kết",UNMATCHED:"Thiếu đối ứng",AMBIGUOUS:"Cần xem xét",INVALID:"Dữ liệu lỗi",OUT_OF_SCOPE:"Ngoài phạm vi",PENDING:"Đang chờ",
  EQUAL:"Bằng nhau",WITHIN_TOLERANCE:"Trong sai số cho phép",AMOUNT_MISMATCH:"Lệch tiền",ATTRIBUTE_MISMATCH:"Khác thuộc tính",
  NOT_COMPARABLE:"Chưa thể so sánh",NOT_EVALUATED:"Chưa so sánh",OPEN:"Chưa xử lý",IN_REVIEW:"Đang xem xét",RESOLVED:"Đã xử lý",
  DISMISSED_WITH_REASON:"Đóng có lý do",MISSING_COUNTERPART:"Thiếu đối ứng",DUPLICATE_KEY:"Trùng khóa",MISSING_FIELD:"Thiếu trường",
  INVALID_DECIMAL:"Số tiền không hợp lệ",UNCERTAIN_MATCH:"Ứng viên chưa chắc chắn",INSUFFICIENT_COVERAGE:"Nguồn chưa đủ kỳ",
  NOT_YET_SETTLED:"Chưa đến hạn quyết toán",RULE_UNVERIFIED:"Chưa đủ điều kiện so sánh",SCHEMA_DRIFT:"Cấu trúc nguồn đã đổi",
};
export const label = (value:string) => reconciliationLabels[value] || value;
