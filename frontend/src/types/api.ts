/** Centralized shared types — mirrors the backend's Pydantic DTOs.
 * These are kept in sync manually until `pnpm gen:api` runs against
 * the backend's openapi.yaml. */

export type TaskStatus =
  | "queued"
  | "running"
  | "success"
  | "failed"
  | "cancelled"
  | "archived";

export type ParseStatus = "pending" | "parsing" | "parsed" | "failed";

export type StageStatus = "pending" | "running" | "success" | "failed";

export type StageName = "outline" | "points" | "svg" | "pptx";

export interface PageMeta {
  total: number | null;
  next_cursor: string | null;
  has_more: boolean;
}

export interface Page<T> {
  items: T[];
  meta: PageMeta;
}

export interface HealthResponse {
  status: "ok" | "degraded";
  version: string;
  queue_length: number;
  db_ok: boolean;
  redis_ok: boolean;
  s3_ok: boolean;
}

export interface GenerationTask {
  id: string;
  owner_id: string;
  prompt: string;
  status: TaskStatus;
  current_stage: StageName | null;
  queue_position: number | null;
  result_pptx_path: string | null;
  style_fit_score: Record<string, number> | null;
  token_consumed: number;
  estimated_tokens: number | null;
  estimated_seconds: number | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  error_message: string | null;
  mode: "knowledge_base" | "general";
  visual_style: string | null;
  communication_mode: string | null;
}

export interface VisualStyleOption {
  id: string;
  name: string;
  character: string;
  best_for: string;
}

export interface CommunicationModeOption {
  id: string;
  name: string;
  narrative_skeleton: string;
  best_for: string;
}

export interface Sample {
  id: string;
  owner_id: string;
  file_name: string;
  file_type: "pptx" | "pdf" | "docx";
  parse_status: ParseStatus;
  parse_page_count: number | null;
  pii_summary: PIISummary | null;
  uploaded_at: string;
  parsed_at: string | null;
  deleted_at: string | null;
}

export interface PIISummary {
  hit_count: number;
  fields: string[];
  actions: Array<{
    field: string;
    start: number;
    end: number;
    score: number;
    replacement: string;
  }>;
}

export interface TraceStage {
  id: string;
  task_id: string;
  stage_name: StageName;
  stage_order: number;
  input_summary: string;
  output_summary: string;
  duration_ms: number;
  status: StageStatus;
  started_at: string | null;
  finished_at: string | null;
  error_message: string | null;
  redo_count: number;
}

export interface Preference {
  id: string; // "P-007"
  owner_id: string;
  source_chains: unknown[];
  rule_text: string;
  applies_to: "cover" | "toc" | "body" | "closing" | "all";
  apply_count: number;
  ignore_count: number;
  last_applied_at: string | null;
  is_active: boolean;
}

export interface SecurityEvent {
  id: string;
  owner_id: string;
  event_type:
    | "pii_hit"
    | "pii_blocked"
    | "pii_replaced"
    | "pii_acknowledged"
    | "unauth_access"
    | "bulk_export"
    | "bulk_delete";
  hit_field: string | null;
  action_taken: "replace" | "block" | "allow";
  related_resource_id: string | null;
  created_at: string;
  details: Record<string, unknown> | null;
}

export interface SlideAsset {
  id: string;
  source_sample_id: string | null;
  page_index: number;
  visual_type:
    | "cover"
    | "toc"
    | "architecture"
    | "flowchart"
    | "data"
    | "body"
    | "closing"
    | "mixed";
  title: string | null;
  body_text: string | null;
  thumbnail_path: string | null;
  color_palette: string[];
  font_family: string | null;
  industry_tags: string[];
  indexed_at: string | null;
  svg_payload?: string;
}

export interface DraftSlide {
  id: string;
  draft_id: string;
  slide_order: number;
  source_type: "reused" | "generated" | "manual";
  material_id: string | null;
  generated_stage_id: string | null;
  title: string | null;
  body_text: string | null;
  notes: string | null;
}

export interface Draft {
  id: string;
  owner_id: string;
  title: string;
  status: "active" | "archived" | "exported";
  overall_style: Record<string, unknown> | null;
  last_saved_revision: number;
  editor_user_id: string | null;
  lock_acquired_at: string | null;
  lock_expires_at: string | null;
  created_at: string;
  updated_at: string;
  slides: DraftSlide[];
}
