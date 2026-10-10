export type Settings = {
  model_id: string;
  width: number;
  height: number;
  steps: number;
  cfg: number;
  seed: string | null;
};
export type PromptSettings = {
  context_size: number;
  max_tokens: number;
  thinking: boolean;
  history_turns: number;
  reasoning_level: "low" | "medium" | "high";
  provider?: "local" | "chatgpt";
  chatgpt_model?: string;
  chatgpt_reasoning_effort?: ChatGPTReasoningEffort | "default";
};
export type ChatGPTReasoningEffort = "none" | "minimal" | "low" | "medium" | "high" | "xhigh" | "max";
export type PromptConfiguration = Partial<Omit<PromptSettings, "provider">>;
export type ChatGPTModel = { slug: string; display_name: string };
export type ChatGPTStatus = {
  connected: boolean;
  plan_enabled: boolean;
  active_account: string | null;
  email: string | null;
  accounts: { id: string; email: string | null; connected: boolean }[];
  login_state: string;
  error_code: string | null;
  welcome_pending: boolean;
  revocation_confirmed?: boolean;
};
export type GenerationDefaults = Record<string, Pick<Settings, "steps" | "cfg">>;
export type ImageModel = {
  id: string;
  name: string;
  family: string;
  family_name: string;
  variant_name: string;
  asset_ids: string[];
  defaults: Pick<Settings, "steps" | "cfg">;
};
export type ProjectInfo = {
  id: string;
  created_at: string;
  active_leaf_id: string | null;
  fork_image_id: string | null;
};
export type ImageItem = {
  id: string;
  width: number;
  height: number;
  request_text: string | null;
  created_at: string;
  parent_image_id: string | null;
  turn_id: string;
  versions: string[];
};
export type UnfinishedRequest = {
  id: string;
  width: number;
  height: number;
  text: string | null;
  status: string;
  error_code: string | null;
  message: string | null;
  turn_id: string | null;
};
export type Project = ProjectInfo & {
  images: ImageItem[];
  unfinished_requests: UnfinishedRequest[];
};
export type ImageDetails = { id: string; prompt: string; settings: Settings; model_name: string };
export type Job = {
  id: string;
  width: number;
  height: number;
  project_id: string;
  request_id: string;
  state: string;
  step: number | null;
  total: number | null;
  image_id: string | null;
  error_code: string | null;
  message?: string | null;
  thinking_enabled?: boolean;
  prompt_text?: string;
  turn_id?: string | null;
};
export type ModelStatus = {
  id: string;
  available: boolean;
  filename?: string | null;
  manual_download?: { url: string; filename: string } | null;
  download?: {
    model_id: string;
    state: string;
    received: number;
    total: number;
    error_code: string | null;
    message?: string | null;
  } | null;
};
export type Bootstrap = {
  language: "ko" | "en";
  project: Project;
  projects: ProjectInfo[];
  settings: Settings;
  generation_defaults: GenerationDefaults;
  image_models: ImageModel[];
  prompt_settings: PromptSettings;
  models?: ModelStatus[];
  chatgpt?: ChatGPTStatus | null;
};
type Result<T> =
  | { ok: true; value: T }
  | { ok: false; error: { code: string; message: string } };
export type Bridge = Record<
  string,
  (...args: unknown[]) => Promise<Result<unknown>>
>;

// Keep the boundary code, rather than freezing the display language at rejection time.
export class BridgeError extends Error {
  constructor(public readonly code: string) {
    super(code);
    this.name = "BridgeError";
  }
}
declare global {
  interface Window {
    pywebview?: { api: Bridge };
  }
}

export async function call<T>(method: string, ...args: unknown[]): Promise<T> {
  const bridge = window.pywebview?.api;
  if (!bridge) throw new BridgeError("DESKTOP_UNAVAILABLE");
  let result: Result<T>;
  try {
    result = (await bridge[method](...args)) as Result<T>;
  } catch {
    // Raw bridge failures can contain implementation details and local paths.
    throw new BridgeError("BRIDGE_FAILED");
  }
  if (!result || typeof result.ok !== "boolean") throw new BridgeError("BRIDGE_FAILED");
  if (!result.ok) {
    if (!result.error || typeof result.error.code !== "string")
      throw new BridgeError("BRIDGE_FAILED");
    throw new BridgeError(result.error.code);
  }
  return result.value;
}
