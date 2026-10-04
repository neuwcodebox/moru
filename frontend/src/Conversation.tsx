import { useLayoutEffect, useRef } from "react";
import type { RefObject } from "react";
import {
  ChevronLeft,
  ChevronRight,
  GitBranch,
  LoaderCircle,
  Pencil,
  RotateCcw,
  User,
} from "lucide-react";
import type { Job, Project, UnfinishedRequest } from "./api";
import GenerationProgress from "./GenerationProgress";
import CopyButton from "./CopyButton";
import ImagePreview from "./ImagePreview";
import { imageFrameStyle } from "./imageFrame";
import { call } from "./api";
import appIcon from "../../docs/ICON.png?inline";

function VersionSelector({
  versions,
  selectedId,
  disabled,
  onSelect,
}: {
  versions: string[];
  selectedId: string;
  disabled: boolean;
  onSelect: (id: string) => void;
}) {
  if (versions.length < 2) return null;
  const index = versions.indexOf(selectedId);
  const move = (offset: number) =>
    onSelect(versions[(index + offset + versions.length) % versions.length]);
  return (
    <div className="branch-selector" aria-label="이미지 버전 선택">
      <button
        aria-label="이전 이미지"
        disabled={disabled}
        onClick={() => move(-1)}
      >
        <ChevronLeft size={16} aria-hidden="true" />
      </button>
      <span>
        {index + 1} / {versions.length}
      </span>
      <button
        aria-label="다음 이미지"
        disabled={disabled}
        onClick={() => move(1)}
      >
        <ChevronRight size={16} aria-hidden="true" />
      </button>
    </div>
  );
}

function RequestFailure({
  request,
  busy,
  onRetry,
}: {
  request: UnfinishedRequest;
  busy: boolean;
  onRetry: (id: string) => void;
}) {
  if (request.status === "pending") return null;
  return (
    <div className="request-error">
      <span>{request.message}</span>
      <button disabled={busy} onClick={() => onRetry(request.id)}>
        <RotateCcw size={14} aria-hidden="true" /> 재시도
      </button>
    </div>
  );
}

export default function Conversation({
  project,
  sources,
  busy,
  inactive,
  job,
  scrollRef,
  followLatest,
  onBottomChange,
  onViewImage,
  onShowPrompt,
  onFork,
  onSelectVersion,
  onRegenerate,
  onRetry,
  activeTurnId,
  onFocusImage,
  onError,
}: {
  project: Project | null;
  sources: Record<string, string>;
  busy: boolean;
  inactive: boolean;
  job: Job | null;
  scrollRef: RefObject<HTMLElement | null>;
  followLatest: RefObject<boolean>;
  onBottomChange: (bottom: boolean) => void;
  onViewImage: (turnId: string) => void;
  onShowPrompt: (id: string) => void;
  onFork: (id: string) => void;
  onSelectVersion: (id: string) => void;
  onRegenerate: (id: string) => void;
  onRetry: (id: string) => void;
  activeTurnId: string | null;
  onFocusImage: (turnId: string) => void;
  onError: (message: string) => void;
}) {
  const content = useRef<HTMLDivElement>(null);
  const previousProject = useRef<string | undefined>(undefined);
  const scrolledTurn = useRef<string | null>(null);
  function follow() {
    if (inactive) return;
    const element = scrollRef.current;
    if (element && followLatest.current)
      element.scrollTop = element.scrollHeight;
  }
  useLayoutEffect(() => {
    if (previousProject.current !== project?.id) {
      previousProject.current = project?.id;
      followLatest.current = true;
      onBottomChange(true);
    }
    follow();
  }, [project, job]);
  useLayoutEffect(() => {
    if (!content.current || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(follow);
    observer.observe(content.current);
    if (scrollRef.current) observer.observe(scrollRef.current);
    return () => observer.disconnect();
  }, [inactive]);
  useLayoutEffect(() => {
    if (inactive || scrolledTurn.current === activeTurnId) return;
    scrolledTurn.current = activeTurnId;
    content.current?.querySelector<HTMLElement>(".turn.is-selected")?.scrollIntoView?.({
      block: "nearest", behavior: "instant",
    });
  }, [activeTurnId, inactive]);
  const pending = project?.unfinished_requests.find(
    (request) => request.id === job?.request_id,
  );
  const generatingTurn = job?.turn_id ?? pending?.turn_id;
  const ungrouped =
    project?.unfinished_requests.filter((request) => !request.turn_id) ?? [];
  return (
    <main
      ref={scrollRef}
      className="conversation"
      inert={inactive}
      aria-label="대화"
      onScroll={(event) => {
        const element = event.currentTarget;
        followLatest.current =
          element.scrollHeight - element.scrollTop - element.clientHeight < 40;
        onBottomChange(followLatest.current);
      }}
    >
      <div ref={content}>
        {project && !job && !project.images.length && !ungrouped.length && (
          <div className="empty">
            <img className="empty-symbol" src={appIcon} alt="" />
            <h1>어떤 장면을 그릴까요?</h1>
            <p>원하는 이미지를 이야기하고, 대화로 다듬어 보세요.</p>
          </div>
        )}
        {!project && (
          <p className="connecting" role="status">
            데스크톱 앱에 연결하는 중…
          </p>
        )}
        {project?.images.map((image) => (
          <div className={`turn ${activeTurnId === image.turn_id ? "is-selected" : ""}`} key={image.turn_id}>
            {image.request_text && (
              <div className="user-row">
                <div className="user-message">{image.request_text}</div>
                <span className="avatar" aria-hidden="true">
                  <User size={18} />
                </span>
              </div>
            )}
            <div className="image-result" onFocusCapture={() => onFocusImage(image.turn_id)}>
              {job && generatingTurn === image.turn_id ? (
                <GenerationProgress job={job} />
              ) : sources[image.id] ? (
                <ImagePreview
                  key={image.id}
                  id={image.id}
                  source={sources[image.id]}
                  width={image.width}
                  height={image.height}
                  inactive={inactive}
                  onOpen={() => onViewImage(image.turn_id)}
                  onFocus={() => onFocusImage(image.turn_id)}
                  onLoad={follow}
                />
              ) : (
                <div
                  className="image-placeholder"
                  role="status"
                  style={imageFrameStyle(image.width, image.height)}
                >
                  <LoaderCircle
                    className="spinner"
                    size={20}
                    aria-hidden="true"
                  />{" "}
                  이미지를 불러오는 중…
                </div>
              )}
              <div className="image-actions">
                <button disabled={busy} onClick={() => onRegenerate(image.id)}>
                  <RotateCcw size={15} aria-hidden="true" /> 다시
                </button>
                <button disabled={busy} onClick={() => onShowPrompt(image.id)}>
                  <Pencil size={15} aria-hidden="true" /> 수정
                </button>
                <CopyButton
                  disabled={!sources[image.id] || (!!job && generatingTurn === image.turn_id)}
                  onCopy={async () => { await call("copy_image", image.id); }}
                  onError={onError}
                />
                <button disabled={busy} onClick={() => onFork(image.id)}>
                  <GitBranch size={15} aria-hidden="true" /> 분기
                </button>
                <VersionSelector
                  versions={image.versions}
                  selectedId={image.id}
                  disabled={busy}
                  onSelect={onSelectVersion}
                />
              </div>
              {project.unfinished_requests
                .filter((request) => request.turn_id === image.turn_id)
                .map((request) => (
                  <RequestFailure
                    key={request.id}
                    request={request}
                    busy={busy}
                    onRetry={onRetry}
                  />
                ))}
            </div>
          </div>
        ))}
        {ungrouped.map((request) => (
          <div className="unfinished" key={request.id}>
            {request.text && (
              <div className="user-row">
                <div className="user-message">{request.text}</div>
              </div>
            )}
            {job?.request_id === request.id && <GenerationProgress job={job} />}
            <RequestFailure request={request} busy={busy} onRetry={onRetry} />
          </div>
        ))}
        {job && !generatingTurn && !pending && <GenerationProgress job={job} />}
      </div>
    </main>
  );
}
