export type TurnStatus = "continue" | "draft" | "complete";

export type ConversationStatus = "active" | "complete";

export type ToolKind = "rag" | "search";

export type InputType = "step" | "pulse" | "sine";

export type ChatRole = "user" | "assistant";

export type HitlOption = {
  label: string;
};

export type HitlPrompt = {
  question: string;
  options: HitlOption[];
  allow_free_text: boolean;
  timeout_sec: number | null;
};

export type SearchHit = {
  source: string;
  snippet: string;
  url: string | null;
};

export type ToolResult = {
  kind: ToolKind;
  items: SearchHit[];
};

export type FileRef = {
  file_id: string;
  name: string;
};

export type ChatMessage = {
  role: ChatRole;
  content: string;
  status?: TurnStatus | null;
  hitl?: HitlPrompt | null;
  tool_results?: ToolResult[];
  attachment_ids?: string[];
};

export type PlantModelResult = {
  system_name: string;
  python_code: string;
  metadata?: Record<string, unknown> | null;
};

export type PlantPayload = PlantModelResult;

export type PlantModelSessionStateOut = {
  draft_count: number;
  latest_draft?: PlantModelResult | null;
};

export type TokenUsageOut = {
  input_tokens: number;
  output_tokens: number;
  estimated_cost: number;
};

export type PlantModelChatRequest = {
  user_message: string;
  messages?: ChatMessage[];
  model?: string;
  session_state?: PlantModelSessionStateOut | null;
  conversation_id?: number | null;
  max_drafts?: number;
  min_user_turns_before_completion?: number;
  attachment_ids?: string[];
  web_search?: boolean;
};

export type PlantModelChatResponse = {
  reply: string;
  status: TurnStatus;
  final_result: PlantModelResult | null;
  session_state: PlantModelSessionStateOut;
  usage: TokenUsageOut | null;
  conversation_id: number | null;
  hitl: HitlPrompt | null;
  tool_results: ToolResult[];
};

export type PlantModelConversationSummary = {
  id: number;
  title: string;
  status: ConversationStatus;
  llm_model: string;
  system_name: string | null;
  user_id: number | null;
  owner_email: string | null;
  created_at: string;
  updated_at: string;
};

export type PlantModelConversationDetail = {
  id: number;
  title: string;
  status: ConversationStatus;
  llm_model: string;
  messages: ChatMessage[];
  session_state: PlantModelSessionStateOut | null;
  final_result: PlantModelResult | null;
  user_id: number | null;
  owner_email: string | null;
  created_at: string;
  updated_at: string;
};

export type PreLaunchConfig = {
  total_simulation_time: number;
  solver_sample_time: number;
  initial_state?: number[];
  default_target?: number[];
};

export type ArtifactCreateRequest = {
  pre_launch: PreLaunchConfig;
  plant?: PlantPayload | null;
  conversation_id?: number | null;
};

export type ArtifactSummary = {
  artifact_id: string;
  system_name: string;
  created_at: string;
  version: string;
};

export type ArtifactCreateResponse = {
  artifact_id: string;
  system_name: string;
  created_at: string;
  version: string;
  warnings: string[];
};

export type ArtifactDetail = {
  artifact_id: string;
  system_name: string;
  created_at: string;
  version: string;
  plant: Record<string, unknown>;
  pre_launch: Record<string, unknown>;
  module_specific: Record<string, unknown>;
  [extra: string]: unknown;
};

export type ArtifactPluginResponse = {
  artifact_id: string;
  plugin_path: string;
  source: string;
};

export type ValidationRequest = {
  plant?: PlantPayload | null;
  pre_launch?: PreLaunchConfig | null;
  conversation_id?: number | null;
};

export type ValidationResponse = {
  ok: boolean;
  errors: string[];
  warnings: string[];
};

export type SimulateRequest = {
  conversation_id?: number | null;
  plant?: PlantPayload | null;
  input_type?: InputType;
  amplitude?: number;
  total_simulation_time: number;
  solver_sample_time: number;
  initial_state?: number[];
  pulse_width?: number | null;
  frequency?: number | null;
};

export type SimulateResponse = {
  t: number[];
  x: number[][];
  u: number[][];
  warnings: string[];
};

export type HealthResponse = {
  status: string;
  service: string;
};

export type UserScopedOptions = {
  userId?: number;
};
