import { useState } from "react";
import { call } from "./api";
import type { ImageDetails } from "./api";
import Modal from "./Modal";
import { modelNames } from "./SettingsDialog";

export default function PromptDialog({
  details,
  onClose,
  onGenerate,
}: {
  details: ImageDetails;
  onClose: () => void;
  onGenerate: (prompt: string) => Promise<void>;
}) {
  const [prompt, setPrompt] = useState(details.prompt);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const s = details.settings;
  return (
    <Modal title="프롬프트" onClose={onClose}>
      <label>
        실제 생성 프롬프트
        <textarea
          className="prompt-editor"
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
        />
      </label>
      <dl className="metadata">
        <div>
          <dt>모델</dt>
          <dd>{modelNames[s.model_id]}</dd>
        </div>
        <div>
          <dt>Width / Height</dt>
          <dd>
            {s.width} / {s.height}
          </dd>
        </div>
        <div>
          <dt>Steps</dt>
          <dd>{s.steps}</dd>
        </div>
        <div>
          <dt>CFG</dt>
          <dd>{s.cfg}</dd>
        </div>
        <div>
          <dt>Seed</dt>
          <dd>{s.seed}</dd>
        </div>
      </dl>
      {message && <p role="status">{message}</p>}
      <div className="modal-actions">
        <button onClick={onClose}>닫기</button>
        <button
          onClick={async () => {
            try {
              await call("copy_prompt", prompt);
              setMessage("복사했습니다.");
            } catch {
              setMessage(
                "복사할 수 없습니다. 프롬프트를 선택해 복사해 주세요.",
              );
            }
          }}
        >
          복사
        </button>
        <button
          className="primary"
          disabled={busy || !prompt.trim()}
          onClick={async () => {
            setBusy(true);
            try {
              await onGenerate(prompt);
              onClose();
            } catch (error) {
              setMessage(
                error instanceof Error
                  ? error.message
                  : "생성 요청에 실패했습니다.",
              );
            } finally {
              setBusy(false);
            }
          }}
        >
          이 프롬프트로 생성
        </button>
      </div>
    </Modal>
  );
}
