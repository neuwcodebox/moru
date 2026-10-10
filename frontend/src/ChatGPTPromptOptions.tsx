import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { call } from "./api";
import type { ChatGPTReasoningEffort, PromptSettings } from "./api";
import { errorMessage } from "./errorMessages";

export default function ChatGPTPromptOptions({ settings, onChange }: {
  settings: PromptSettings;
  onChange: (settings: PromptSettings) => void;
}) {
  const { t } = useTranslation("dialogs");
  const [efforts, setEfforts] = useState<ChatGPTReasoningEffort[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const effort = settings.chatgpt_reasoning_effort ?? "default";
  const supported = effort === "default" || efforts.includes(effort);

  useEffect(() => {
    let disposed = false;
    setLoading(true);
    setEfforts([]);
    setError(null);
    void call<ChatGPTReasoningEffort[]>("get_chatgpt_reasoning_efforts", settings.chatgpt_model ?? "")
      .then((choices) => { if (!disposed) setEfforts(choices); })
      .catch((cause) => { if (!disposed) setError(cause); })
      .finally(() => { if (!disposed) setLoading(false); });
    return () => { disposed = true; };
  }, [settings.chatgpt_model]);

  return <>
    <label>{t("settings.reasoningLevel")}
      <select value={effort} disabled={loading}
        onChange={(event) => onChange({ ...settings,
          chatgpt_reasoning_effort: event.target.value as PromptSettings["chatgpt_reasoning_effort"] })}>
        <option value="default">{t("chatgpt.reasoning.default")}</option>
        {!supported && <option value={effort} disabled>{t(`chatgpt.reasoning.${effort}`)}</option>}
        {efforts.map((value) => <option key={value} value={value}>{t(`chatgpt.reasoning.${value}`)}</option>)}
      </select>
    </label>
    {!loading && error == null && !supported && <p role="alert">{t("chatgpt.reasoningUnavailable")}</p>}
    {error != null && <p role="alert">{errorMessage(error, "CHATGPT_UNAVAILABLE")}</p>}
  </>;
}
