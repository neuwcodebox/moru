import type { ChatGPTStatus } from "../../api";

export function canUseChatGPT(status: ChatGPTStatus | null | undefined, model: string | undefined): boolean {
  return !!status?.connected && status.plan_enabled && !!model && status.login_state !== "waiting";
}
