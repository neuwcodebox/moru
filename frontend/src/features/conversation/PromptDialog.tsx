import { useTranslation } from "react-i18next";
import { useState } from "react";
import { call } from "../../api";
import type { ImageDetails } from "../../api";
import Modal from "../../components/Modal";
import { WandSparkles } from "lucide-react";
import CopyButton from "../../components/CopyButton";
import { errorMessage } from "../../errorMessages";

export default function PromptDialog({
  details,
  onClose,
  onGenerate,
}: {
  details: ImageDetails;
  onClose: () => void;
  onGenerate: (prompt: string) => Promise<void>;
}) {
  const { t } = useTranslation("dialogs");
  const [prompt, setPrompt] = useState(details.prompt);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<unknown>(null);
  const s = details.settings;
  return (
    <Modal title={t("prompt.title")} onClose={onClose}>
      <label>
        {t("prompt.actualPrompt")}
        <textarea
          className="prompt-editor"
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
        />
      </label>
      <dl className="metadata">
        <div>
          <dt>{t("common.model")}</dt>
          <dd>{details.model_name}</dd>
        </div>
        <div>
          <dt>{t("common.dimensions")}</dt>
          <dd>
            {s.width} / {s.height}
          </dd>
        </div>
        <div>
          <dt>{t("common.steps")}</dt>
          <dd>{s.steps}</dd>
        </div>
        <div>
          <dt>{t("common.cfg")}</dt>
          <dd>{s.cfg}</dd>
        </div>
        <div>
          <dt>{t("common.seed")}</dt>
          <dd>{s.seed}</dd>
        </div>
      </dl>
      {message != null && <p role="alert">{errorMessage(message, "GENERATION_REQUEST_FAILED")}</p>}
      <div className="modal-actions">
        <button onClick={onClose}>{t("common.close")}</button>
        <CopyButton
          onCopy={async () => {
            setMessage(null);
            await call("copy_prompt", prompt);
          }}
          onError={setMessage}
        />
        <button
          className="primary"
          disabled={busy || !prompt.trim()}
          onClick={async () => {
            setBusy(true);
            try {
              await onGenerate(prompt);
              onClose();
            } catch (error) {
              setMessage(error);
            } finally {
              setBusy(false);
            }
          }}
        >
          <WandSparkles size={15} aria-hidden="true" /> {t("prompt.generate")}
        </button>
      </div>
    </Modal>
  );
}
