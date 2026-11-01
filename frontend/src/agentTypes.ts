import type { AssistantAnswer, AssistantContext } from "./assistantTypes";
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
};
export type QueryResult = {
    query: Query;
    source_id: string;
    fields: string[];
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
};
export type AgentIntent = {
    intent: string;
    dataset_ids?: string[];
    run_id?: string | null;
    key_value?: string | null;
    query?: Query | null;
    questions?: string[];
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
    plan: Plan | null;
    suggestions: Suggestions | null;
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
    status: string;
    transformations: string[];
} | {
    type: "table";
    result: QueryResult;
} | {
    type: "facts";
    result: {
        run: Run | null;
        snapshot: Snapshot | null;
        group: Group | null;
    };
    answer: AssistantAnswer | null;
} | Chart | {
    type: "download";
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
        steps: {
            tool: string;
            resource_id: string;
            status: string;
            job_id: string | null;
        }[];
        reviews: Review[];
        blocks: AgentBlock[];
        model_calls: number;
        error_code: string | null;
    };
};
