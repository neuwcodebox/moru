import { useTranslation } from "react-i18next";
import { useRef, useState } from "react";
import type { ChatGPTStatus, ImageModel, PromptSettings, Settings } from "../../api";
import Modal from "../../components/Modal";
import { errorMessage } from "../../errorMessages";
import ImageModelSelect from "../models/ImageModelSelect";
import PromptOptions from "./PromptOptions";
import { canUseChatGPT } from "../chatgpt/availability";

const resolutions = [
  [1024, 1024],
  [832, 1216],
  [1216, 832],
  [768, 1344],
  [1344, 768],
];

export default function SettingsDialog({
  settings,
  imageModels,
  promptSettings,
  chatgpt = null,
  localReady = true,
  onClose,
  onSave,
}: {
  settings: Settings;
  imageModels: ImageModel[];
  promptSettings: PromptSettings;
  chatgpt?: ChatGPTStatus | null;
  localReady?: boolean;
  onClose: () => void;
  onSave: (settings: Settings, promptSettings: PromptSettings) => Promise<void>;
}) {
  const { t } = useTranslation("dialogs");
  const [draft, setDraft] = useState(settings);
  const [promptDraft, setPromptDraft] = useState(promptSettings);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const form = useRef<HTMLFormElement>(null);
  const savingPending = useRef(false);
  async function close() {
    if (savingPending.current) return;
    const changed = Object.entries(draft).some(([field, value]) => value !== settings[field as keyof Settings]) ||
      Object.entries(promptDraft).some(([field, value]) => value !== promptSettings[field as keyof PromptSettings]);
    if (!changed) {
      onClose();
      return;
    }
    setError(null);
    const invalid = form.current?.querySelector<HTMLInputElement>("input:invalid, select:invalid");
    const details = invalid?.closest("details");
    if (details) details.open = true;
    if (!form.current?.reportValidity()) return;
    savingPending.current = true;
    setSaving(true);
    try {
      if (promptDraft.max_tokens >= promptDraft.context_size) {
        throw { code: "OUTPUT_TOKENS_EXCEED_CONTEXT" };
      }
      await onSave(draft, promptDraft);
      onClose();
    } catch (cause) {
      setError(cause);
    } finally {
      savingPending.current = false;
      setSaving(false);
    }
  }
  function number(field: "width" | "height" | "steps" | "cfg", value: string) {
    setDraft({ ...draft, [field]: value === "" ? Number.NaN : Number(value) });
  }
  return (
    <Modal title={t("settings.title")} onClose={close}>
      <form ref={form} aria-busy={saving} onSubmit={(event) => event.preventDefault()}>
        <fieldset disabled={saving} className="settings-fields">
          <ImageModelSelect models={imageModels} modelId={draft.model_id} disabled={saving}
            onChange={(model) => setDraft({ ...draft, model_id: model.id, ...model.defaults })} />
          <p className="hint">{t("settings.modelHint")}</p>
          <label>
            {t("settings.imageSize")}
            <select
              aria-label={t("settings.resolutionPreset")}
              value={`${draft.width}x${draft.height}`}
              onChange={(event) => {
                if (event.target.value === "custom") return;
                const [width, height] = event.target.value.split("x").map(Number);
                setDraft({ ...draft, width, height });
              }}
            >
              <option value="custom">{t("settings.custom")}</option>
              {resolutions.map(([w, h]) => (
                <option key={w} value={`${w}x${h}`}>
                  {w} × {h}
                </option>
              ))}
              {!resolutions.some(
                ([w, h]) => w === draft.width && h === draft.height,
              ) && (
                <option value={`${draft.width}x${draft.height}`}>
                  {t("settings.custom")}
                </option>
              )}
            </select>
          </label>
          <div className="field-grid">
            <label>
              {t("common.width")}
              <input
                type="number"
                min={64}
                max={4096}
                step={16}
                required
                value={Number.isNaN(draft.width) ? "" : draft.width}
                onChange={(e) => number("width", e.target.value)}
              />
            </label>
            <label>
              {t("common.height")}
              <input
                type="number"
                min={64}
                max={4096}
                step={16}
                required
                value={Number.isNaN(draft.height) ? "" : draft.height}
                onChange={(e) => number("height", e.target.value)}
              />
            </label>
            <label>
              {t("common.steps")}
              <input
                type="number"
                min={1}
                max={150}
                required
                value={Number.isNaN(draft.steps) ? "" : draft.steps}
                onChange={(e) => number("steps", e.target.value)}
              />
            </label>
            <label>
              {t("common.cfg")}
              <input
                type="number"
                min={0}
                max={30}
                step="any"
                required
                value={Number.isNaN(draft.cfg) ? "" : draft.cfg}
                onChange={(e) => number("cfg", e.target.value)}
              />
            </label>
          </div>
          <label>
            {t("common.seed")}
            <input
              inputMode="numeric"
              pattern="[0-9]*"
              placeholder={t("common.auto")}
              value={draft.seed ?? ""}
              onChange={(event) =>
                setDraft({ ...draft, seed: event.target.value || null })
              }
            />
          </label>
          <p className="hint">{t("settings.seedHint")}</p>
          <hr className="model-section-divider" />
          <label>{t("chatgpt.provider")}
            <select value={promptDraft.provider ?? "local"} disabled={saving}
              onChange={(event) => setPromptDraft({ ...promptDraft,
                provider: event.target.value as PromptSettings["provider"] })}>
              <option value="local" disabled={!localReady}>{t("chatgpt.local")}</option>
              <option value="chatgpt" disabled={!canUseChatGPT(chatgpt, promptDraft.chatgpt_model)}>ChatGPT</option>
            </select>
          </label>
          <p className="hint">{t("chatgpt.setupHint")}</p>
          <details className="advanced-settings">
            <summary>{t("settings.advanced")}</summary>
            <fieldset disabled={saving} className="prompt-options">
              <PromptOptions settings={promptDraft} local={promptDraft.provider !== "chatgpt"}
                onChange={setPromptDraft} />
            </fieldset>
          </details>
          {error != null && <p role="alert">{errorMessage(error, "SAVE_SETTINGS_FAILED")}</p>}
          <div className="modal-actions">
            <button type="button" onClick={close}>
              {t("common.close")}
            </button>
          </div>
        </fieldset>
      </form>
    </Modal>
  );
}
