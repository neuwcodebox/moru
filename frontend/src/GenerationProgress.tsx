import { useTranslation } from "react-i18next";
import { Image, LoaderCircle, WandSparkles } from "lucide-react";
import type { Job } from "./api";
import PromptText from "./PromptText";
import { imageFrameStyle } from "./imageFrame";

function progressLabel(job: Job): string {
  switch (job.state) {
    case "queued": return "queued";
    case "loading_prompt_model": return "loadingPromptModel";
    case "prompting": return job.thinking_enabled && !job.prompt_text ? "thinking" : "writingPrompt";
    case "loading_model": return "loadingModel";
    default: return "generating";
  }
}

export default function GenerationProgress({ job }: { job: Job }) {
  const { t } = useTranslation();
  const writing = job.state === "prompting";
  const preparingPrompt = writing || job.state === "loading_prompt_model";
  return (
    <section
      className="generation-placeholder"
      aria-label={t("generationProgress")}
      style={imageFrameStyle(job.width, job.height)}
    >
      <div className="generation-stage" role="status" aria-live="polite">
        <LoaderCircle className="spinner" size={18} aria-hidden="true" />
        <span>{t(progressLabel(job))}</span>
        {job.step != null && job.total != null && (
          <span className="step-count">
            {job.step} / {job.total}
          </span>
        )}
      </div>
      <div className="generation-canvas">
        {!job.prompt_text && (
          <>
            {preparingPrompt ? (
              <WandSparkles size={32} aria-hidden="true" />
            ) : (
              <Image size={32} aria-hidden="true" />
            )}
            <span>
              {preparingPrompt
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
