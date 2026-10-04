import { useTranslation } from "react-i18next";
import { useState } from "react";
import type { GenerationDefaults, PromptSettings, Settings } from "./api";
import Modal from "./Modal";
import { errorMessage } from "./errorMessages";
import { imageModelNames } from "./modelNames";
import { Check } from "lucide-react";
const resolutions = [
  [1024, 1024],
  [832, 1216],
  [1216, 832],
  [768, 1344],
  [1344, 768],
];

export default function SettingsDialog({
  settings,
  generationDefaults,
  promptSettings,
  onClose,
  onSave,
}: {
  settings: Settings;
  generationDefaults: GenerationDefaults;
  promptSettings: PromptSettings;
  onClose: () => void;
  onSave: (settings: Settings, promptSettings: PromptSettings) => Promise<void>;
}) {
  const { t } = useTranslation("dialogs");
  const [draft, setDraft] = useState(settings);
  const [promptDraft, setPromptDraft] = useState(promptSettings);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);
  function number(field: "width" | "height" | "steps" | "cfg", value: string) {
    setDraft({ ...draft, [field]: value === "" ? Number.NaN : Number(value) });
  }
  return (
    <Modal title={t("settings.title")} onClose={onClose}>
      <form
        onSubmit={async (event) => {
          event.preventDefault();
          setSaving(true);
          setError(null);
          try {
            if (promptDraft.max_tokens >= promptDraft.context_size) {
              throw { code: "OUTPUT_TOKENS_EXCEED_CONTEXT" };
            }
            await onSave(draft, promptDraft);
            onClose();
          } catch (error) {
            setError(error);
          } finally {
            setSaving(false);
          }
        }}
      >
        <label>
          {t("common.model")}
          <select
            value={draft.model_id}
            onChange={(event) =>
              setDraft({
                ...draft,
                model_id: event.target.value,
                ...generationDefaults[event.target.value],
              })
            }
          >
            {Object.entries(imageModelNames).map(([id, name]) => (
              <option key={id} value={id}>
                {name}
              </option>
            ))}
          </select>
        </label>
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
        <details className="advanced-settings">
          <summary>{t("settings.advanced")}</summary>
          <div className="field-grid">
            <label>
              {t("settings.contextSize")}
              <input
                type="number"
                min={1024}
                max={32768}
                required
                value={
                  Number.isNaN(promptDraft.context_size)
                    ? ""
                    : promptDraft.context_size
                }
                onChange={(event) =>
                  setPromptDraft({
                    ...promptDraft,
                    context_size:
                      event.target.value === ""
                        ? Number.NaN
                        : Number(event.target.value),
                  })
                }
              />
            </label>
            <label>
              {t("settings.maxTokens")}
              <input
                type="number"
                min={1}
                max={32767}
                required
                value={
                  Number.isNaN(promptDraft.max_tokens)
                    ? ""
                    : promptDraft.max_tokens
                }
                onChange={(event) =>
                  setPromptDraft({
                    ...promptDraft,
                    max_tokens:
                      event.target.value === ""
                        ? Number.NaN
                        : Number(event.target.value),
                  })
                }
              />
            </label>
          </div>
          <label>
            {t("settings.historyTurns")}
            <input
              type="number"
              min={0}
              max={20}
              required
              value={
                Number.isNaN(promptDraft.history_turns)
                  ? ""
                  : promptDraft.history_turns
              }
              onChange={(event) =>
                setPromptDraft({
                  ...promptDraft,
                  history_turns:
                    event.target.value === ""
                      ? Number.NaN
                      : Number(event.target.value),
                })
              }
            />
          </label>
          <p className="hint">
            {t("settings.historyHint")}
          </p>
          <label className="checkbox-field">
            <input
              type="checkbox"
              checked={promptDraft.thinking}
              onChange={(event) =>
                setPromptDraft({
                  ...promptDraft,
                  thinking: event.target.checked,
                })
              }
            />
            {t("settings.thinking")}
          </label>
          <label>
            {t("settings.reasoningLevel")}
            <select
              value={promptDraft.reasoning_level}
              disabled={!promptDraft.thinking}
              onChange={(event) =>
                setPromptDraft({
                  ...promptDraft,
                  reasoning_level: event.target.value as PromptSettings["reasoning_level"],
                })
              }
            >
              <option value="low">{t("settings.reasoningLow")}</option>
              <option value="medium">{t("settings.reasoningMedium")}</option>
              <option value="high">{t("settings.reasoningHigh")}</option>
            </select>
          </label>
          <p className="hint">
            {t("settings.reasoningHint")}
          </p>
          <p className="hint">
            {t("settings.contextHint")}
          </p>
          <p className="hint">
            {t("settings.persistHint")}
          </p>
        </details>
        {error != null && <p role="alert">{errorMessage(error, "SAVE_SETTINGS_FAILED")}</p>}
        <div className="modal-actions">
          <button type="button" onClick={onClose}>
            {t("common.close")}
          </button>
          <button className="primary" disabled={saving}>
            <Check size={16} aria-hidden="true" /> {t("common.save")}
          </button>
        </div>
      </form>
    </Modal>
  );
}
