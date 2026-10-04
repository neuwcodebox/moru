import { Image, LoaderCircle, WandSparkles } from "lucide-react";
import type { Job } from "./api";
import PromptText from "./PromptText";
import { imageFrameStyle } from "./imageFrame";

export default function GenerationProgress({ job }: { job: Job }) {
  const writing = job.state === "prompting";
  const label =
    job.state === "queued"
      ? "생성 대기 중…"
      : writing
        ? job.thinking_enabled && !job.prompt_text
          ? "생각 중…"
          : "프롬프트 작성 중…"
        : job.state === "loading_model"
          ? "이미지 모델을 불러오는 중…"
          : "이미지 생성 중…";
  return (
    <section
      className="generation-placeholder"
      aria-label="생성 진행"
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
                ? "장면을 준비하고 있어요"
                : "곧 이미지가 여기에 나타나요"}
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
          aria-label="이미지 생성 단계"
        />
      )}
    </section>
  );
}
