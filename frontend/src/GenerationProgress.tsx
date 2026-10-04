import { useTranslation } from "react-i18next";
import { Image, LoaderCircle, WandSparkles } from "lucide-react";
import type { Job } from "./api";
import PromptText from "./PromptText";
import { imageFrameStyle } from "./imageFrame";

export default function GenerationProgress({ job }: { job: Job }) {
  const { t } = useTranslation();
  const writing = job.state === "prompting";
  const label =
    job.state === "queued"
      ? t("queued")
      : writing
        ? job.thinking_enabled && !job.prompt_text
          ? t("thinking")
          : t("writingPrompt")
        : job.state === "loading_model"
          ? t("loadingModel")
          : t("generating");
  return (
    <section
      className="generation-placeholder"
      aria-label={t("generationProgress")}
      style={imageFrameStyle(job.width, job.height)}
    >
      <div className="generation-stage" role="status" aria-live="polite">
        <LoaderCircle className="spinner" size={18} aria-hidden="true" />
        <span>{label}</span>
        {job.step != null && job.total != null && (
          <span className="step-count">
            {job.step} / {job.total}
          </span>
        )}
      </div>
      <div className="generation-canvas">
        {!job.prompt_text && (
          <>
            {writing ? (
              <WandSparkles size={32} aria-hidden="true" />
            ) : (
              <Image size={32} aria-hidden="true" />
            )}
            <span>
              {writing
                ? t("preparingScene")
                : t("imageComing")}
            </span>
          </>
        )}
        {job.prompt_text && (
          <PromptText follow>{job.prompt_text}</PromptText>
        )}
      </div>
      {job.step != null && job.total != null && (
        <progress
          value={job.step}
          max={job.total}
          aria-label={t("generationSteps")}
        />
      )}
    </section>
  );
}
