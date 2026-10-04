import type { Job } from "./api";

const progressNames: Record<string, string> = {
  queued: "생성 대기",
  loading_model: "이미지 모델 준비",
  generating: "이미지 생성",
};

export default function GenerationProgress({
  job,
  onCancel,
}: {
  job: Job;
  onCancel: () => void;
}) {
  const thinking = job.state === "prompting";
  return (
    <div
      className={`progress${thinking ? " thinking" : ""}`}
      role="status"
      aria-live="polite"
    >
      <span className="spinner" />
      <span>
        {thinking ? "생각 중…" : (progressNames[job.state] ?? "이미지 생성")}
        {!thinking && job.step != null && job.total != null
          ? ` · ${job.step} / ${job.total}`
          : ""}
      </span>
      <button onClick={onCancel}>취소</button>
    </div>
  );
}
