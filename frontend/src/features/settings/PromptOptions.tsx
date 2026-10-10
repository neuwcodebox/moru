import { useTranslation } from "react-i18next";
import type { PromptSettings } from "../../api";
import ChatGPTPromptOptions from "../chatgpt/PromptOptions";

export default function PromptOptions({ settings, local, onChange }: {
  settings: PromptSettings;
  local: boolean;
  onChange: (settings: PromptSettings) => void;
}) {
  const { t } = useTranslation("dialogs");
  function number(field: "context_size" | "max_tokens" | "history_turns", value: string) {
    onChange({ ...settings, [field]: value === "" ? Number.NaN : Number(value) });
  }
  return <>
    <label>
      {t("settings.historyTurns")}
      <input type="number" min={0} max={20} required
        value={Number.isNaN(settings.history_turns) ? "" : settings.history_turns}
        onChange={(event) => number("history_turns", event.target.value)} />
    </label>
    <p className="hint">{t("settings.historyHint")}</p>
    {local && <>
      <div className="field-grid">
        <label>
          {t("settings.contextSize")}
          <input type="number" min={1024} max={32768} required
            value={Number.isNaN(settings.context_size) ? "" : settings.context_size}
            onChange={(event) => number("context_size", event.target.value)} />
        </label>
        <label>
          {t("settings.maxTokens")}
          <input type="number" min={1} max={32767} required
            value={Number.isNaN(settings.max_tokens) ? "" : settings.max_tokens}
            onChange={(event) => number("max_tokens", event.target.value)} />
        </label>
      </div>
      <label className="checkbox-field">
        <input type="checkbox" checked={settings.thinking}
          onChange={(event) => onChange({ ...settings, thinking: event.target.checked })} />
        {t("settings.thinking")}
      </label>
      <label>
        {t("settings.reasoningLevel")}
        <select value={settings.reasoning_level} disabled={!settings.thinking}
          onChange={(event) => onChange({ ...settings,
            reasoning_level: event.target.value as PromptSettings["reasoning_level"] })}>
          <option value="low">{t("settings.reasoningLow")}</option>
          <option value="medium">{t("settings.reasoningMedium")}</option>
          <option value="high">{t("settings.reasoningHigh")}</option>
        </select>
      </label>
      <p className="hint">{t("settings.reasoningHint")}</p>
      <p className="hint">{t("settings.contextHint")}</p>
    </>}
    {!local && <ChatGPTPromptOptions settings={settings} onChange={onChange} />}
  </>;
}
