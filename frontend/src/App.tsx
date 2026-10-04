import { useEffect, useRef, useState } from "react";
import {
  ArrowUp,
  ArrowDown,
  Box,
  Plus,
  Settings2,
  Sparkles,
  Square,
  X,
} from "lucide-react";
import { call } from "./api";
import type {
  Bootstrap,
  ImageDetails,
  Job,
  ModelStatus,
  Project,
  ProjectInfo,
  PromptSettings,
  GenerationDefaults,
  Settings,
} from "./api";
import Lightbox from "./Lightbox";
import PromptDialog from "./PromptDialog";
import SettingsDialog from "./SettingsDialog";
import ModelsDialog from "./ModelsDialog";
import Conversation from "./Conversation";

export default function App() {
  const [project, setProject] = useState<Project | null>(null);
  const [projects, setProjects] = useState<ProjectInfo[]>([]);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [generationDefaults, setGenerationDefaults] = useState<GenerationDefaults>(
    {},
  );
  const [promptSettings, setPromptSettings] = useState<PromptSettings | null>(
    null,
  );
  const [text, setText] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [acting, setActing] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [error, setError] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [models, setModels] = useState<ModelStatus[]>([]);
  const [modelsOpen, setModelsOpen] = useState(false);
  const [details, setDetails] = useState<ImageDetails | null>(null);
  const [viewer, setViewer] = useState<string | null>(null);
  const [sources, setSources] = useState<Record<string, string>>({});
  const input = useRef<HTMLTextAreaElement>(null);
  const conversation = useRef<HTMLElement>(null);
  const followLatest = useRef(true);
  const [atBottom, setAtBottom] = useState(true);
  const busy = acting || job !== null;

  useEffect(() => {
    let disposed = false;
    async function bootstrap() {
      try {
        const result = await call<Bootstrap>("bootstrap");
        if (disposed) return;
        setProject(result.project);
        setProjects(result.projects);
        setSettings(result.settings);
        setGenerationDefaults(result.generation_defaults);
        setPromptSettings(result.prompt_settings);
        setError("");
        setModels(result.models ?? []);
        const required = [
          "prompt",
          result.settings.model_id,
          "text_encoder",
          "vae",
        ];
        if (
          result.models?.some(
            (model) => required.includes(model.id) && !model.available,
          )
        )
          setModelsOpen(true);
      } catch (error) {
        if (!disposed)
          setError(
            error instanceof Error ? error.message : "앱을 불러올 수 없습니다.",
          );
      }
    }
    if (window.pywebview?.api) void bootstrap();
    window.addEventListener("pywebviewready", bootstrap);
    return () => {
      disposed = true;
      window.removeEventListener("pywebviewready", bootstrap);
    };
  }, []);

  useEffect(() => {
    if (!job) return;
    const jobId = job.id;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const result = await call<Job>("get_job", jobId);
        if (disposed) return;
        if (["completed", "failed", "cancelled"].includes(result.state)) {
          const refreshed = await call<Project>(
            "get_project",
            result.project_id,
          );
          if (disposed) return;
          setProject(refreshed);
          setJob(null);
          setStopping(false);
          if (result.message) setError(result.message);
          input.current?.focus();
          return;
        }
        setJob(result);
      } catch (error) {
        if (!disposed)
          setError(
            error instanceof Error
              ? error.message
              : "진행 상태를 확인할 수 없습니다.",
          );
      }
      if (!disposed) timer = setTimeout(poll, 300);
    }
    void poll();
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [job?.id]);

  useEffect(() => {
    let disposed = false;
    for (const image of project?.images ?? []) {
      if (sources[image.id]) continue;
      call<string>("get_image_source", image.id)
        .then((source) => {
          if (!disposed)
            setSources((previous) => ({ ...previous, [image.id]: source }));
        })
        .catch((error) => {
          if (!disposed)
            setError(
              error instanceof Error
                ? error.message
                : "이미지를 불러올 수 없습니다.",
            );
        });
    }
    return () => {
      disposed = true;
    };
  }, [project]);

  async function act(action: () => Promise<void>) {
    setActing(true);
    setError("");
    try {
      await action();
    } catch (error) {
      setError(error instanceof Error ? error.message : "요청에 실패했습니다.");
    } finally {
      setActing(false);
    }
  }
  async function submit() {
    if (!project || busy || !text.trim()) return;
    await act(async () => {
      await startGeneration("submit_request", project.id, text);
      setText("");
    });
  }
  async function startGeneration(method: string, ...args: unknown[]) {
    const next = await call<Job>(method, ...args);
    setJob(next);
    try {
      setProject(await call<Project>("get_project", next.project_id));
    } catch (error) {
      // The request was accepted; keep observing its job instead of offering another submission.
      setError(
        error instanceof Error ? error.message : "대화를 불러올 수 없습니다.",
      );
    }
  }
  function cancelGeneration() {
    if (!job || stopping) return;
    setStopping(true);
    void call("cancel_job", job.id).catch((error) => {
      setStopping(false);
      setError(error instanceof Error ? error.message : "중지할 수 없습니다.");
    });
  }

  return (
    <div className="app">
      <header>
        <span className="brand">
          moru
          <Sparkles className="brand-dot" size={18} aria-hidden="true" />
        </span>
        <div className="header-actions">
          <select
            aria-label="작업 기록"
            value={project?.id ?? ""}
            disabled={busy}
            onChange={(event) =>
              void act(async () =>
                setProject(
                  await call<Project>("open_project", event.target.value),
                ),
              )
            }
          >
            {projects.map((p, index) => (
              <option key={p.id} value={p.id}>
                작업 {projects.length - index} ·{" "}
                {new Date(p.created_at).toLocaleDateString("ko-KR")}
              </option>
            ))}
          </select>
          <button disabled={busy} onClick={() => setModelsOpen(true)}>
            <Box size={16} aria-hidden="true" /> 모델 설정
          </button>
        </div>
      </header>
      <Conversation
        project={project}
        sources={sources}
        busy={busy}
        job={job}
        scrollRef={conversation}
        followLatest={followLatest}
        onBottomChange={setAtBottom}
        onViewImage={setViewer}
        onShowPrompt={(id) =>
          void act(async () => {
            setDetails(await call<ImageDetails>("get_image_details", id));
          })
        }
        onFork={(id) =>
          void act(async () => {
            if (!project) return;
            setProject(await call<Project>("fork", project.id, id));
            setProjects(await call<ProjectInfo[]>("list_projects"));
            setText("");
            input.current?.focus();
          })
        }
        onSelectVersion={(id) =>
          void act(async () => {
            if (project)
              setProject(await call<Project>("select_version", project.id, id));
          })
        }
        onRegenerate={(id) =>
          void act(async () => {
            await startGeneration("regenerate", id);
          })
        }
        onRetry={(id) =>
          void act(async () => {
            await startGeneration("retry_request", id);
          })
        }
      />
      <footer>
        {!atBottom && (
          <button
            className="scroll-bottom"
            aria-label="맨 아래로"
            title="맨 아래로"
            onClick={() => {
              followLatest.current = true;
              conversation.current?.scrollTo({
                top: conversation.current.scrollHeight,
                behavior: "instant",
              });
              setAtBottom(true);
            }}
          >
            <ArrowDown size={18} aria-hidden="true" />
          </button>
        )}
        {error && (
          <div className="error-banner" role="alert">
            <span>{error}</span>
            <button aria-label="오류 메시지 닫기" onClick={() => setError("")}>
              <X size={16} aria-hidden="true" />
            </button>
          </div>
        )}
        <div className="composer-tools">
          <button
            className="new-project"
            disabled={busy || !project}
            onClick={() =>
              void act(async () => {
                setProject(await call<Project>("create_project"));
                setProjects(await call<ProjectInfo[]>("list_projects"));
                setText("");
                input.current?.focus();
              })
            }
          >
            <Plus size={16} aria-hidden="true" /> 새 작업
          </button>
        </div>
        <form
          className="composer"
          onSubmit={(event) => {
            event.preventDefault();
            if (job) cancelGeneration();
            else void submit();
          }}
        >
          <button
            type="button"
            className="settings-button"
            aria-label="생성 설정"
            title="생성 설정"
            disabled={!settings}
            onClick={() => setSettingsOpen(true)}
          >
            <Settings2 size={20} aria-hidden="true" />
          </button>
          <textarea
            ref={input}
            aria-label="이미지 요청"
            placeholder="이미지를 설명하거나 수정 요청을 입력하세요…"
            rows={1}
            value={text}
            onChange={(event) => setText(event.target.value)}
            disabled={busy || !project}
            onKeyDown={(event) => {
              if (
                event.key === "Enter" &&
                !event.shiftKey &&
                !event.nativeEvent.isComposing &&
                event.keyCode !== 229
              ) {
                event.preventDefault();
                void submit();
              }
            }}
          />
          <button
            className="send-button"
            aria-label={job ? "중지" : "전송"}
            title={job ? (stopping ? "중지하는 중…" : "생성 중지") : "전송"}
            disabled={job ? stopping : busy || !text.trim() || !project}
          >
            {job ? (
              <Square size={17} fill="currentColor" aria-hidden="true" />
            ) : (
              <ArrowUp size={22} aria-hidden="true" />
            )}
          </button>
        </form>
      </footer>
      {settingsOpen && settings && promptSettings && (
        <SettingsDialog
          settings={settings}
          generationDefaults={generationDefaults}
          promptSettings={promptSettings}
          onClose={() => setSettingsOpen(false)}
          onSave={async (draft, promptDraft) => {
            setSettings(
              await call<Settings>("update_settings", draft, promptDraft),
            );
            setPromptSettings(promptDraft);
          }}
        />
      )}
      {modelsOpen && (
        <ModelsDialog
          initial={models}
          onUpdate={setModels}
          onClose={() => setModelsOpen(false)}
        />
      )}
      {details && (
        <PromptDialog
          details={details}
          onClose={() => setDetails(null)}
          onGenerate={async (prompt) => {
            await startGeneration("generate_from_prompt", details.id, prompt);
          }}
        />
      )}
      {viewer && <Lightbox source={viewer} onClose={() => setViewer(null)} />}
    </div>
  );
}
