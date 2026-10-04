import { useEffect, useRef } from "react";
import type { Job, Project } from "./api";
import GenerationProgress from "./GenerationProgress";

function BranchSelector({
  siblings,
  selectedId,
  disabled,
  onSelect,
}: {
  siblings: string[];
  selectedId: string;
  disabled: boolean;
  onSelect: (id: string) => void;
}) {
  if (siblings.length < 2) return null;
  const index = siblings.indexOf(selectedId);
  const move = (offset: number) =>
    onSelect(siblings[(index + offset + siblings.length) % siblings.length]);
  return (
    <div className="branch-selector" aria-label="분기 선택">
      <button
        aria-label="이전 분기"
        disabled={disabled}
        onClick={() => move(-1)}
      >
        ‹
      </button>
      <span>
        {index + 1} / {siblings.length}
      </span>
      <button
        aria-label="다음 분기"
        disabled={disabled}
        onClick={() => move(1)}
      >
        ›
      </button>
    </div>
  );
}

export default function Conversation({
  project,
  sources,
  busy,
  job,
  onViewImage,
  onShowPrompt,
  onFork,
  onSelectBranch,
  onRetry,
  onCancel,
}: {
  project: Project | null;
  sources: Record<string, string>;
  busy: boolean;
  job: Job | null;
  onViewImage: (source: string) => void;
  onShowPrompt: (id: string) => void;
  onFork: (id: string) => void;
  onSelectBranch: (id: string) => void;
  onRetry: (id: string) => void;
  onCancel: () => void;
}) {
  const bottom = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bottom.current?.scrollIntoView?.({ behavior: "smooth" });
  }, [project, job?.state]);

  return (
    <main className="conversation" aria-label="대화">
      {project &&
        !project.images.length &&
        !project.unfinished_requests.length && (
          <div className="empty">
            <div className="empty-symbol">✦</div>
            <h1>어떤 장면을 그릴까요?</h1>
            <p>원하는 이미지를 이야기하고, 대화로 다듬어 보세요.</p>
          </div>
        )}
      {!project && (
        <p className="connecting" role="status">
          데스크톱 앱에 연결하는 중…
        </p>
      )}
      {project?.images.map((image, index) => (
        <div className="turn" key={image.id}>
          {image.request_text && (
            <div className="user-row">
              <div className="user-message">{image.request_text}</div>
              <span className="avatar" aria-hidden="true">
                ♙
              </span>
            </div>
          )}
          <div className="image-result">
            {sources[image.id] ? (
              <button
                className="image-button"
                aria-label="이미지 전체 화면 보기"
                onClick={() => onViewImage(sources[image.id])}
              >
                <img src={sources[image.id]} alt="생성 이미지" />
              </button>
            ) : (
              <div className="image-placeholder" role="status">
                이미지를 불러오는 중…
              </div>
            )}
            <div className="image-actions">
              <button disabled={busy} onClick={() => onShowPrompt(image.id)}>
                프롬프트
              </button>
              <button disabled={busy} onClick={() => onFork(image.id)}>
                ⑂ Fork
              </button>
              {index === 0 && (
                <BranchSelector
                  siblings={image.siblings}
                  selectedId={image.id}
                  disabled={busy}
                  onSelect={onSelectBranch}
                />
              )}
              {project.images[index + 1] && (
                <BranchSelector
                  siblings={project.images[index + 1].siblings}
                  selectedId={project.images[index + 1].id}
                  disabled={busy}
                  onSelect={onSelectBranch}
                />
              )}
            </div>
          </div>
        </div>
      ))}
      {project?.unfinished_requests.map((request) => (
        <div className="unfinished" key={request.id}>
          {request.text && (
            <div className="user-row">
              <div className="user-message">{request.text}</div>
            </div>
          )}
          {request.status !== "pending" && (
            <div className="request-error">
              <span>{request.message}</span>
              <button disabled={busy} onClick={() => onRetry(request.id)}>
                재시도
              </button>
            </div>
          )}
        </div>
      ))}
      {job?.state === "prompting" && (
        <GenerationProgress job={job} onCancel={onCancel} />
      )}
      <div ref={bottom} />
    </main>
  );
}
