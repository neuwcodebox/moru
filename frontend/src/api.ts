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
};
export type ProjectInfo = {
  id: string;
  created_at: string;
  active_leaf_id: string | null;
  fork_image_id: string | null;
};
export type ImageItem = {
  id: string;
  request_text: string | null;
  created_at: string;
  parent_image_id: string | null;
  turn_id: string;
  versions: string[];
};
export type UnfinishedRequest = {
  id: string;
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
export type ImageDetails = { id: string; prompt: string; settings: Settings };
export type Job = {
  id: string;
  project_id: string;
  request_id: string;
  state: string;
  step: number | null;
  total: number | null;
  image_id: string | null;
  error_code: string | null;
  message?: string | null;
  thinking_enabled?: boolean;
  thinking_text?: string;
  prompt_text?: string;
  turn_id?: string | null;
};
export type ModelStatus = {
  id: string;
  available: boolean;
  filename?: string | null;
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
  project: Project;
  projects: ProjectInfo[];
  settings: Settings;
  prompt_settings: PromptSettings;
  models?: ModelStatus[];
};
type Result<T> =
  | { ok: true; value: T }
  | { ok: false; error: { code: string; message: string } };
export type Bridge = Record<
  string,
  (...args: unknown[]) => Promise<Result<unknown>>
>;
declare global {
  interface Window {
    pywebview?: { api: Bridge };
  }
}

export async function call<T>(method: string, ...args: unknown[]): Promise<T> {
  if (!window.pywebview?.api)
    throw new Error("데스크톱 앱 연결을 기다리고 있습니다.");
  const result = (await window.pywebview.api[method](...args)) as Result<T>;
  if (!result.ok) throw new Error(result.error.message);
  return result.value;
}
