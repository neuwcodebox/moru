import { useTranslation } from "react-i18next";
import { useId, useRef, useState } from "react";
import { call } from "../../api";
import type { ImageDetails } from "../../api";
import Modal from "../../components/Modal";
import { WandSparkles } from "lucide-react";
import CopyButton from "../../components/CopyButton";
import { errorMessage } from "../../errorMessages";
import RegionCanvas from "./RegionCanvas";
import type { MaskCanvas } from "./RegionCanvas";
import type { EditDraft } from "./editDraft";

export default function PromptDialog({
  details,
  onClose,
  onGenerate,
  source,
  draft,
  onDraft,
  onRegionGenerate,
  regionReady = false,
  regionSupported = true,
  onPrepare,
  onReturnFocus,
}: {
  details: ImageDetails;
  onClose: () => void;
  onGenerate: (prompt: string) => Promise<void>;
  source?: string;
  draft?: EditDraft;
  onDraft?: (draft: EditDraft) => void;
  onRegionGenerate?: (content: string, mask: string) => Promise<void>;
  regionReady?: boolean;
  regionSupported?: boolean;
  onPrepare?: () => void;
  onReturnFocus?: () => void;
}) {
  const { t } = useTranslation("dialogs");
  const [state, setState] = useState<EditDraft>(draft ?? { prompt: details.prompt, content: "", strokes: [] });
  const prompt = state.prompt;
  const setPrompt = (prompt: string) => update({ prompt });
  const [tab, setTab] = useState<"prompt" | "region">(details.edit_tab ?? "prompt");
  const [regionVisited, setRegionVisited] = useState(details.edit_tab === "region");
  const paint = useRef<MaskCanvas>(null);
  const submitting = useRef(false);
  const [busy, setBusy] = useState(false);
  const [tabSaving, setTabSaving] = useState(false);
  const [message, setMessage] = useState<unknown>(null);
  const s = details.settings;
  const tooltipId = useId();
  const generateDisabled = busy || (tab === "prompt" ? !prompt.trim() :
    !regionReady || !source || !onRegionGenerate || !state.content.trim() || !state.strokes.length);
  const generationInfo = [
    t("region.generationInfo"),
    `${t("common.model")}: ${details.model_name}`,
    `${t("common.dimensions")}: ${s.width} × ${s.height}`,
    `${t("common.steps")}: ${s.steps}`,
    `${t("common.cfg")}: ${s.cfg}`,
    `${t("common.seed")}: ${s.seed ?? t("common.auto")}`,
  ].join("\n");
  function update(values: Partial<EditDraft>) {
    setState((previous) => {
      const next = { ...previous, ...values };
      onDraft?.(next);
      return next;
    });
  }
  async function changeTab(next: "prompt" | "region") {
    if (tabSaving) return;
    setMessage(null);
    setTabSaving(true);
    try {
      await call("set_edit_tab", next);
      setTab(next);
      if (next === "region") setRegionVisited(true);
    } catch (error) { setMessage(error); }
    finally { setTabSaving(false); }
  }
  return (
    <Modal title={t("region.title")} onClose={() => { if (!submitting.current) onClose(); }}
      className={`image-edit-dialog${tab === "prompt" ? " image-edit-prompt-mode" : s.width > s.height ? " image-edit-wide" : s.width < s.height ? " image-edit-tall" : ""}`} onReturnFocus={onReturnFocus}
      toolbar={<div className="image-edit-heading">
      <h2>{t("region.title")}</h2>
      <div className="edit-tabs" role="tablist" aria-label={t("region.mode")}>
        <button role="tab" aria-selected={tab === "prompt"} disabled={busy || tabSaving}
          onClick={() => void changeTab("prompt")}>{t("region.promptTab")}</button>
        <button role="tab" aria-selected={tab === "region"} disabled={busy || tabSaving}
          onClick={() => void changeTab("region")}>{t("region.regionTab")}</button>
      </div>
      </div>}>
      <div className="image-edit-body">
      <div hidden={tab !== "prompt"} className="image-edit-prompt">
      <label className="image-edit-prompt-field">
        <span className="sr-only">{t(details.generation_method === "region" ? "region.scenePrompt" : "prompt.actualPrompt")}</span>
        <textarea
          className="prompt-editor"
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
        />
      </label>
      {details.generation_method === "region" && <details className="region-execution">
        <summary>{t("region.executionPrompt")}</summary><p>{details.execution_prompt}</p>
      </details>}
      </div>
      <div hidden={tab !== "region"} className="region-editor">
        {!source && <p role="status">{t("translation:imageLoading")}</p>}
        {source && regionVisited && <RegionCanvas ref={paint} source={source} width={s.width} height={s.height}
          strokes={state.strokes} disabled={busy}
          onChange={(strokes) => update({ strokes })} />}
      </div>
      </div>
      <div className="image-edit-footer">
      {tab === "region" && !regionReady && <p role="status" className="image-edit-notice">{t("region.notReady")} {onPrepare &&
        <button onClick={onPrepare} disabled={busy}>{t(regionSupported ? "models.title" : "settings.title")}</button>}</p>}
      {message != null && <p role="alert" className="image-edit-notice">{errorMessage(message, "GENERATION_REQUEST_FAILED")}</p>}
      <div className={`image-edit-submit ${tab === "region" ? "region-submit" : ""}`}>
      {tab === "region" ? <label className="region-content">
        <span className="sr-only">{t("region.content")}</span>
        <textarea value={state.content} disabled={busy} rows={2}
          placeholder={t("region.placeholder")} maxLength={8000}
          onChange={(event) => update({ content: event.target.value })} />
      </label> : null}
      <div className="modal-actions">
        {tab === "prompt" &&
        <CopyButton
          onCopy={async () => {
            setMessage(null);
            await call("copy_prompt", prompt);
          }}
          onError={setMessage}
        />}
        <span className="generation-action" tabIndex={generateDisabled ? 0 : undefined} aria-describedby={tooltipId}>
        <button
          className="primary"
          aria-describedby={tooltipId}
          disabled={generateDisabled}
          onClick={async () => {
            if (submitting.current) return;
            submitting.current = true;
            setBusy(true);
            try {
              if (tab === "region") {
                const mask = paint.current?.mask();
                if (!mask) throw { code: "REGION_EMPTY_MASK" };
                await onRegionGenerate?.(state.content, mask);
              } else await onGenerate(prompt);
              onClose();
            } catch (error) {
              setMessage(error);
            } finally {
              setBusy(false);
              submitting.current = false;
            }
          }}
        >
          <WandSparkles size={15} aria-hidden="true" /> {t(tab === "prompt" ? "prompt.generate" : "region.generate")}
        </button>
        <span role="tooltip" id={tooltipId} className="generation-tooltip">{generationInfo}</span>
        </span>
      </div>
      </div>
      </div>
    </Modal>
  );
}
