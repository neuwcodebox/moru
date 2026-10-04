import { useTranslation } from "react-i18next";
import { useEffect, useState } from "react";
import { call } from "./api";
import type { ModelStatus } from "./api";
import Modal from "./Modal";
import { imageModelNames } from "./modelNames";
import { errorMessage } from "./errorMessages";
import { CheckCircle2, Download, FolderOpen, Square } from "lucide-react";
export default function ModelsDialog({
  initial,
  onUpdate,
  onClose,
}: {
  initial: ModelStatus[];
  onUpdate: (models: ModelStatus[]) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation("dialogs");
  const [models, setModels] = useState(initial);
  const [error, setError] = useState<{ cause: unknown; fallbackCode: string } | null>(null);
  const [acting, setActing] = useState(false);
  const downloading = models.some((model) =>
    ["queued", "downloading"].includes(model.download?.state ?? ""),
  );
  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const fresh = await call<ModelStatus[]>("get_model_status");
        if (disposed) return;
        setModels(fresh);
        onUpdate(fresh);
      } catch (error) {
        if (!disposed)
          setError({ cause: error, fallbackCode: "MODEL_STATUS_FAILED" });
      }
      if (!disposed) timer = setTimeout(poll, 500);
    }
    void poll();
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, []);
  async function action(method: string, id: string) {
    setActing(true);
    setError(null);
    try {
      const fresh = await call<ModelStatus[]>(method, id);
      setModels(fresh);
      onUpdate(fresh);
    } catch (error) {
      setError({ cause: error, fallbackCode: "MODEL_PREPARATION_FAILED" });
    } finally {
      setActing(false);
    }
  }
  return (
    <Modal title={t("models.title")} onClose={onClose}>
      <p className="hint">
        {t("models.hint")}
      </p>
      <div className="model-list">
        {models.map((model) => {
          const name = imageModelNames[model.id] ?? t(`models.names.${model.id}`, { defaultValue: model.id });
          const d = model.download;
          const active = d && ["queued", "downloading"].includes(d.state);
          return (
            <div className="model-row" key={model.id}>
              <div className="model-label">
                <strong>{name}</strong>
                <span className="hint">
                  {model.available ? (
                    <>
                      <CheckCircle2 size={14} aria-hidden="true" /> {t("models.ready")}
                    </>
                  ) : (
                    t("models.notReady")
                  )}
                </span>
              </div>
              <p className="model-filename" title={model.filename ?? undefined}>
                {model.filename ?? t("models.noFile")}
              </p>
              {active ? (
                <div className="download-progress">
                  <progress
                    value={d.received}
                    max={d.total}
                    aria-label={t("models.progress", { model: name })}
                  />
                  <span>{Math.floor((d.received * 100) / d.total)}%</span>
                  <button
                    disabled={acting}
                    onClick={() =>
                      void action("cancel_model_download", model.id)
                    }
                  >
                    <Square size={12} aria-hidden="true" /> {t("models.cancel")}
                  </button>
                </div>
              ) : (
                <div className="model-actions">
                  <button
                    disabled={acting || downloading}
                    onClick={() => void action("select_local_model", model.id)}
                  >
                    <FolderOpen size={14} aria-hidden="true" /> {t("models.selectFile")}
                  </button>
                  {!model.available && (
                    <button
                      disabled={acting || downloading}
                      onClick={() => void action("download_model", model.id)}
                    >
                      <Download size={14} aria-hidden="true" /> {t("models.download")}
                    </button>
                  )}
                </div>
              )}
              {(d?.message || d?.error_code) && <p role="alert">{errorMessage(d)}</p>}
            </div>
          );
        })}
      </div>
      {error && <p role="alert">{errorMessage(error.cause, error.fallbackCode)}</p>}
      <div className="modal-actions">
        <button onClick={onClose}>{t("common.close")}</button>
      </div>
    </Modal>
  );
}
