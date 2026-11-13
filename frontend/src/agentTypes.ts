import type { AssistantAnswer, AssistantContext, ModelChoice } from "./assistantTypes";
import type { Group, Plan, Run, Slot, Snapshot, Suggestions } from "./reconciliationTypes";
export type DraftField = {
    source_field: string;
    target_id: string;
    name: string;
    data_type: "string" | "decimal" | "date";
    business_key: boolean;
    semantic_metric: string | null;
    amount_basis: string | null;
    currency: string | null;
    unit: string | null;
    locale: "en-US" | "vi-VN" | null;
    date_format: string | null;
    timezone: string | null;
    question: string;
};
export type NormalizationDraft = {
    table_id: string;
    entity_kind: string;
    grain: string;
    fields: DraftField[];
};
export type SharedMappingFacts = {
    revision: number;
    reviewKeys: string[];
    business_key: string;
    entity_kind: string;
    grain: string;
    timezone: string;
    amount_basis: string;
    semantic_metric: string;
};
export type MappingAssessment = {
    draft: NormalizationDraft; source_rows: number; verified_fields: number; pending_fields: number;
    checks: {field_id:string;name:string;state:string;messages:string[];error_counts:Record<string,number>;affected_rows:number;
        date_kind?: "calendar" | "offset" | "local" | null; date_formats?: string[]}[];
    currency_counts?: Record<string, number>;
    key_candidates?: {field_id:string; name:string; reference:boolean; missing_rows:number; duplicate_rows:number}[];
    related_keys?:{table_id:string;source_name:string;fields:string[];shared_keys:number;left_duplicate_rows:number;right_duplicate_rows:number;missing_key_rows:number}[];currencies?:string[];questions:string[];preflight_ready:boolean;predicted_invalid_rows:number|null;error_counts:Record<string,number>;source_sha256:string;
};
export type Query = {
    project_id: string;
    source_kind: string;
    source_id: string;
    select_fields: string[];
    filters: {
        field_id: string;
        op: string;
        value: string | string[] | null;
    }[];
    sort: {
        field_id: string;
        descending: boolean;
    }[];
    group_by: string[];
    aggregations: {
        op: string;
        field_id: string | null;
    }[];
    offset: number;
    limit: number;
    null_policy: "PRESERVE";
    result_scope: "ALL_MATCHING";
    currency_field: string | null;
    metric_id?: string | null;
    source_measure_id?: string;
    calendar_bucket?: "day" | "month";
};
export type QueryResult = {
    query: Query;
    source_id: string;
    fields: string[];
    field_labels?: Record<string,string>;
    rows: Record<string, unknown>[];
    total_count: number;
    input_count: number;
    offset: number;
    limit: number;
    truncated: boolean;
    evidence_complete: boolean;
    verification_status: string;
    quality_status: string | null;
    source_refs: string[];
    warnings: string[];
    measure_units?: Record<string, string>;
    source_evidence?: {
        source_name: string;
        canonical_id: string;
        mapping_id: string;
        schema_revision: number;
        grain: string;
        measure: { field_id: string; name: string; semantic_metric: string; currency: string; unit: string } | null;
        source_rows: number;
        invalid_rows: number;
        excluded_rows: number;
        matching_rows: number;
        counted_rows: number;
        observed_first: string | null;
        observed_last: string | null;
        sql: string;
    };
};
export type AgentIntent = {
    intent: string;
    dataset_ids?: string[];
    run_id?: string | null;
    key_value?: string | null;
    query?: Query | null;
    questions?: string[];
    export_format?: "csv" | "xlsx";
    export_scope?: "FULL_RUN" | "DISPLAYED_QUERY" | null;
};
export type Review = {
    resource_label?: string | null;
    id: string;
    kind: "MAPPING" | "RECONCILIATION" | "CLARIFICATION";
    resource_id: string;
    nonce: string;
    fingerprint: string;
    expires_at: string;
    state: string;
    question: string;
    reason: string;
    expected_effects: string[];
    normalization_draft: NormalizationDraft | null;
    extraction_review_required?: boolean | null;
    plan: Plan | null;
    suggestions: Suggestions | null;
    planning_candidates?: { id: string; plan: Plan; overlap: number;
        left_distinct_keys: number; right_distinct_keys: number;
        left_rows: number; right_rows: number }[];
    source_evidence?: {
        canonical_id: string;
        name: string;
        uploaded_at: string | null;
        dataset_revision: number;
        mapping_revision: number;
        quality_revision: number;
        valid_rows: number;
        invalid_rows: number;
        excluded_rows: number;
        excluded_amounts: { field: string; amount: string; currency: string }[];
        excluded_amounts_unavailable: boolean;
        exclusion_reasons: string[];
        observed_dates: { field: string; first: string; last: string }[];
        observation_timezone: string;
    }[];
    scope_check_pending?: boolean;
    planning_request: Omit<Partial<Plan>, "left" | "right"> & {
        left: Partial<Slot> & {
            canonical_id: string;
        };
        right: Partial<Slot> & {
            canonical_id: string;
        };
    } | null;
    reply_intent: AgentIntent | null;
    reply_questions: string[];
    pending_reply_job_id: string | null;
    options?: { id: string; label: string; intent: AgentIntent }[];
};
export type Chart = {
    type: "chart";
    title: string;
    unit: string;
    population: number;
    population_definition: string;
    completeness: string;
    points: {
        label: string;
        value: string;
    }[];
    source_refs: string[];
    verification_status: string;
    period_start: string | null;
    period_end: string | null;
    timezone: string | null;
};
export type SourceStatusLine = {
    name: string;
    sheet: string | null;
    status: string;
    original_rows: number | null;
    canonical_rows: number | null;
    valid_rows: number | null;
    invalid_rows: number | null;
    excluded_rows: number | null;
};
export type AgentBlock = {
    type: "progress";
    text: string;
} | {
    type: "dataset_summary";
    dataset_id: string;
    table_id: string;
    canonical_id: string;
    name: string;
    rows: number;
    invalid_rows: number;
    excluded_rows?: number;
    status: string;
    transformations: string[];
    show_issue_rows?: boolean;
    quality_draft?: { source_row_id: string; field: string; code: string; value: string; reason: string; row_index: number } | null;
} | {
    type: "table";
    result: QueryResult;
    title?: string;
} | {
    type: "source_status";
    source_count: number;
    ready_count: number;
    items: SourceStatusLine[];
    totals: SourceStatusLine | null;
} | {
    type: "source_comparison";
    name: string;
    row: number;
    scope: "RAW" | "PREPARED" | "CANONICAL";
    fields: {field:string; original:string|null; processed:string|null; outcome:string}[];
} | {
    type: "facts";
    observation?: {
        pair: string;
        source_names: [string, string];
        observed_start: string;
        observed_end: string;
        duplicate_keys: number;
    };
    result: {
        run: Run | null;
        snapshot: Snapshot | null;
        group: Group | null;
    };
    answer: AssistantAnswer | null;
} | Chart | {
    type: "download";
    source_table?: boolean;
    displayed_query?: boolean;
    discrepancies_only?: boolean;
    export_id: string;
    run_id: string;
    format: string;
};
export type Workflow = {
    id: string;
    conversation_id: string;
    context: AssistantContext;
    state: string;
    updated_at: string;
    detail: {
        intent: AgentIntent | null;
        prepare_upload?: boolean;
        steps: {
            tool: string;
            resource_id: string;
            status: string;
            job_id: string | null;
        }[];
        reviews: Review[];
        blocks: AgentBlock[];
        model_calls: number;
    model_choice?: ModelChoice | null;
        error_code: string | null;
        resumable_job_id?: string | null;
        query_selection?: { query: Query; group_ids: string[] } | null;
    };
};
