import { useState } from "react";
import type { PromptSettings, Settings } from "./api";
import Modal from "./Modal";
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
  promptSettings,
  onClose,
  onSave,
}: {
  settings: Settings;
  promptSettings: PromptSettings;
  onClose: () => void;
  onSave: (settings: Settings, promptSettings: PromptSettings) => Promise<void>;
}) {
  const [draft, setDraft] = useState(settings);
  const [promptDraft, setPromptDraft] = useState(promptSettings);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  function number(field: "width" | "height" | "steps" | "cfg", value: string) {
    setDraft({ ...draft, [field]: value === "" ? Number.NaN : Number(value) });
  }
  return (
    <Modal title="생성 설정" onClose={onClose}>
      <form
        onSubmit={async (event) => {
          event.preventDefault();
          setSaving(true);
          setError("");
          try {
            if (promptDraft.max_tokens >= promptDraft.context_size) {
              throw new Error(
                "출력 토큰 한도는 컨텍스트 크기보다 작아야 합니다.",
              );
            }
            await onSave(draft, promptDraft);
            onClose();
          } catch (error) {
            setError(
              error instanceof Error
                ? error.message
                : "설정을 저장할 수 없습니다.",
            );
          } finally {
            setSaving(false);
          }
        }}
      >
        <label>
          모델
          <select
            value={draft.model_id}
            onChange={(event) =>
              setDraft({ ...draft, model_id: event.target.value })
            }
          >
            {Object.entries(imageModelNames).map(([id, name]) => (
              <option key={id} value={id}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <label>
          이미지 크기
          <select
            aria-label="해상도 프리셋"
            value={`${draft.width}x${draft.height}`}
            onChange={(event) => {
              if (event.target.value === "custom") return;
              const [width, height] = event.target.value.split("x").map(Number);
              setDraft({ ...draft, width, height });
            }}
          >
            <option value="custom">직접 입력</option>
            {resolutions.map(([w, h]) => (
              <option key={w} value={`${w}x${h}`}>
                {w} × {h}
              </option>
            ))}
            {!resolutions.some(
              ([w, h]) => w === draft.width && h === draft.height,
            ) && (
              <option value={`${draft.width}x${draft.height}`}>
                직접 입력
              </option>
            )}
          </select>
        </label>
        <div className="field-grid">
          <label>
            Width
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
            Height
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
            Steps
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
            CFG
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
          Seed
          <input
            inputMode="numeric"
            pattern="[0-9]*"
            placeholder="Auto"
            value={draft.seed ?? ""}
            onChange={(event) =>
              setDraft({ ...draft, seed: event.target.value || null })
            }
          />
        </label>
        <p className="hint">Seed를 비워 두면 매번 자동으로 결정합니다.</p>
        <details className="advanced-settings">
          <summary>고급 · 프롬프트 LLM</summary>
          <div className="field-grid">
            <label>
              컨텍스트 크기
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
              출력 토큰 한도
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
            Thinking 사용
          </label>
          <p className="hint">
            컨텍스트는 입력과 출력을 합친 크기입니다. 출력 한도에는 thinking
            토큰도 포함됩니다. 큰 컨텍스트는 GPU 메모리를 더 사용합니다.
          </p>
          <p className="hint">
            변경한 값은 다음 생성부터 적용되며 앱 재시작 후에도 유지됩니다.
          </p>
        </details>
        {error && <p role="alert">{error}</p>}
        <div className="modal-actions">
          <button type="button" onClick={onClose}>
            닫기
          </button>
          <button className="primary" disabled={saving}>
            <Check size={16} aria-hidden="true" /> 저장
          </button>
        </div>
      </form>
    </Modal>
  );
}
