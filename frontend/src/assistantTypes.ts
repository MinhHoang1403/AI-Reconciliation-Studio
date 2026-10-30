import type { Plan, Snapshot } from "./reconciliationTypes";

export type AssistantContext = {
  project_id: string;
  run_id?: string | null;
  dataset_id?: string | null;
  group_id?: string | null;
  case_id?: string | null;
};
export type Suggestion =
  | "OPEN_EXCEPTIONS"
  | "OPEN_EVIDENCE"
  | "OPEN_RULE"
  | "OPEN_DATA"
  | "OPEN_REPORT"
  | "OPEN_RECONCILIATION";
export type FactReference = {
  id: string;
  run_id: string;
  snapshot_id: string;
  group_id?: string | null;
  member_id?: string | null;
  file_id?: string | null;
  source_table_id?: string | null;
  sheet?: string | null;
  row?: number | null;
};
export type AssistantAnswer = {
  status: string;
  mode: string;
  request_count: number;
  fact_set: {
    id: string;
    context: AssistantContext;
    verification_status: string;
    snapshot: Snapshot | null;
    rule_id: string | null;
    rule_revision: number | null;
    references: FactReference[];
  };
  lines: {
    classification: string;
    text: string;
    fact_id?: string | null;
    reference_ids: string[];
  }[];
  proposal: {
    approved_rule_ids: string[];
    questions: string[];
    confirmation_required: true;
    required_sources: 2 | 3;
    requested_month: number | null;
    requested_year: number | null;
  } | null;
  suggestions: Suggestion[];
};
export type Conversation = {
  id: string;
  context: AssistantContext;
  title: string;
  created_at: string;
  archived: boolean;
};
export type AssistantMessage = {
  id: string;
  job_id: string;
  role: "user" | "assistant";
  text: string;
  context: AssistantContext;
  answer: AssistantAnswer | null;
  created_at: string;
};
export type ConversationPage = {
  conversation: Conversation;
  items: AssistantMessage[];
  has_more: boolean;
};
export type AssistantRule = { id: string; revision: number; plan: Plan };
