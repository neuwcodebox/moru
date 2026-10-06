import { useTranslation } from "react-i18next";
import { useEffect, useState } from "react";
import { call } from "./api";
import type { ImageModel, ModelStatus } from "./api";
import Modal from "./Modal";
import ImageModelSelect from "./ImageModelSelect";
import { errorMessage } from "./errorMessages";
import { CheckCircle2, Download, FolderOpen, Square } from "lucide-react";

const downloadActive = (model: ModelStatus) =>
  ["queued", "downloading"].includes(model.download?.state ?? "");

export default function ModelsDialog({
  initial, imageModels, initialModelId, onUpdate, onClose,
}: {
  initial: ModelStatus[];
  imageModels: ImageModel[];
  initialModelId: string;
  onUpdate: (models: ModelStatus[]) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation("dialogs");
  const [models, setModels] = useState(initial);
  const [viewedModelId, setViewedModelId] = useState(initialModelId);
  const [error, setError] = useState<{ cause: unknown; fallbackCode: string } | null>(null);
  const [acting, setActing] = useState(false);
  const downloading = models.some(downloadActive);
  const viewedModel = imageModels.find((model) => model.id === viewedModelId);
  const assetIds = viewedModel?.asset_ids ?? [];
  const asset = (id: string): ModelStatus => models.find((model) => model.id === id) ?? { id, available: false };
  const ready = assetIds.length > 0 && assetIds.every((id) => asset(id).available);
  const otherDownloads = models.filter((model) =>
    model.id !== "prompt" && !assetIds.includes(model.id) &&
    (downloadActive(model) || model.download?.state === "failed"),
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
        if (!disposed) setError({ cause: error, fallbackCode: "MODEL_STATUS_FAILED" });
      }
      if (!disposed) timer = setTimeout(poll, 500);
    }
    void poll();
    return () => { disposed = true; clearTimeout(timer); };
  }, [onUpdate]);

  async function action(method: string, id: string) {
    setActing(true);
    setError(null);
    try {
      const fresh = await call<ModelStatus[]>(method, id);
      setModels(fresh);
      onUpdate(fresh);
    } catch (error) {
      setError({ cause: error, fallbackCode: "MODEL_PREPARATION_FAILED" });
    } finally { setActing(false); }
  }

  function file(model: ModelStatus) {
    const name = imageModels.find((image) => image.id === model.id)?.name ??
      t(`models.names.${model.id}`, { defaultValue: model.id });
    return <ModelFileRow key={model.id} model={model} name={name}
      busy={acting} downloading={downloading} onAction={action} />;
  }

  return (
    <Modal title={t("models.title")} onClose={onClose}>
      <p className="hint">{t("models.hint")}</p>
      <section className="model-section" aria-label={t("models.names.prompt")}>
        {file(asset("prompt"))}
      </section>
      <section className="model-section" aria-label={t("models.imageSection")}>
        <h3>{t("models.imageSection")}</h3>
        <ImageModelSelect models={imageModels} modelId={viewedModelId} disabled={acting}
          onChange={(model) => setViewedModelId(model.id)} />
        <p className="model-readiness" role="status">
          {t(ready ? "models.imageReady" : "models.imageNotReady")}
        </p>
        <div className="model-list">{assetIds.map((id) => file(asset(id)))}</div>
      </section>
      {otherDownloads.length > 0 && <section className="model-section" aria-label={t("models.otherDownloads")}>
        <h3>{t("models.otherDownloads")}</h3>
        {otherDownloads.map(file)}
      </section>}
      {error && <p role="alert">{errorMessage(error.cause, error.fallbackCode)}</p>}
      <div className="modal-actions">
        <button type="button" onClick={onClose}>{t("common.close")}</button>
      </div>
    </Modal>
  );
}

function ModelFileRow({ model, name, busy, downloading, onAction }: {
  model: ModelStatus;
  name: string;
  busy: boolean;
  downloading: boolean;
  onAction: (method: string, id: string) => Promise<void>;
}) {
  const { t } = useTranslation("dialogs");
  const d = model.download;
  return (
    <div className="model-row" role="group" aria-label={name}>
      <div className="model-label">
        {model.id === "prompt" ? <h3>{name}</h3> : <strong>{name}</strong>}
        <span className="hint">{model.available
          ? <><CheckCircle2 size={14} aria-hidden="true" /> {t("models.ready")}</>
          : t("models.notReady")}</span>
      </div>
      <p className="model-filename" title={model.filename ?? undefined}>
        {model.filename ?? t("models.noFile")}
      </p>
      {d && downloadActive(model) ? <div className="download-progress">
        <progress value={d.received} max={d.total} aria-label={t("models.progress", { model: name })} />
        <span>{Math.floor((d.received * 100) / d.total)}%</span>
        <button type="button" disabled={busy} onClick={() => void onAction("cancel_model_download", model.id)}>
          <Square size={12} aria-hidden="true" /> {t("models.cancel")}
        </button>
      </div> : <div className="model-actions">
        <button type="button" disabled={busy || downloading} onClick={() => void onAction("select_local_model", model.id)}>
          <FolderOpen size={14} aria-hidden="true" /> {t("models.selectFile")}
        </button>
        {!model.available && <button type="button" disabled={busy || downloading} onClick={() => void onAction("download_model", model.id)}>
          <Download size={14} aria-hidden="true" /> {t("models.download")}
        </button>}
      </div>}
      {(d?.message || d?.error_code) && <p role="alert">{errorMessage(d)}</p>}
      {!model.available && model.manual_download && <details className="manual-download" open={d?.state === "failed"}>
        <summary>{t("models.manualDownload")}</summary>
        <p className="hint">{t("models.manualInstructions")}</p>
        <p className="model-filename">{model.manual_download.filename}</p>
        <a href={model.manual_download.url} target="_blank" rel="noopener noreferrer">{t("models.filePage")}</a>
      </details>}
    </div>
  );
}
