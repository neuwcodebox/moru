import { useTranslation } from "react-i18next";
import { Image, LoaderCircle, WandSparkles } from "lucide-react";
import type { Job } from "../../api";
import PromptText from "../../components/PromptText";
import { imageFrameStyle } from "./imageFrame";

function progressLabel(job: Job): string {
  switch (job.state) {
    case "queued": return "queued";
    case "loading_prompt_model": return "loadingPromptModel";
    case "thinking": return "thinking";
    case "searching_tags": return "searchingTags";
    case "prompting": return job.region_edit ? "writingRegionPrompt" :
      job.thinking_enabled && !job.prompt_text ? "thinking" : "writingPrompt";
    case "writing_region_prompt": return "writingRegionPrompt";
    case "writing_scene_prompt": return "writingScenePrompt";
    case "loading_model": return "loadingModel";
    default: return "generating";
  }
}

export default function GenerationProgress({ job }: { job: Job }) {
  const { t } = useTranslation();
  const preparingPrompt = ["prompting", "thinking", "searching_tags", "loading_prompt_model",
    "writing_region_prompt", "writing_scene_prompt"].includes(job.state);
  return (
    <section
      className="generation-placeholder"
      aria-label={t("generationProgress")}
      style={imageFrameStyle(job.width, job.height)}
    >
      <div className="generation-stage" role="status" aria-live="polite">
        <LoaderCircle className="spinner" size={18} aria-hidden="true" />
        <span>
          {job.state === "searching_tags" && job.found_tag_count != null
            ? t("searchingTagsWithCount", { count: job.found_tag_count })
            : t(progressLabel(job))}
        </span>
        {job.step != null && job.total != null && (
          <span className="step-count">
            {job.step} / {job.total}
          </span>
        )}
      </div>
      <div className="generation-canvas">
        {job.region_edit && job.prompt_text ? (
          <div className="region-prompt-progress">
            <div role="group" aria-label={t("regionPrompt")}>
              <PromptText follow label={t("regionPrompt")}>{job.prompt_text}</PromptText>
            </div>
            {(job.state === "writing_scene_prompt" || job.scene_prompt_text) &&
              <div role="group" aria-label={t("scenePrompt")}>
                <PromptText follow label={t("scenePrompt")}>
                  {job.scene_prompt_text || t("writingScenePrompt")}
                </PromptText>
              </div>}
          </div>
        ) : !job.prompt_text ? (
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
        ) : (
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
