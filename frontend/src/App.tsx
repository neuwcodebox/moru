import { errorMessage } from "./errorMessages";
import { useTranslation } from "react-i18next";
import { useEffect, useRef, useState } from "react";
import {
  ArrowUp,
  ArrowDown,
  Box,
  Plus,
  Settings2,
  GitBranch,
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
import appIcon from "../../docs/ICON.png?inline";

export default function App() {
  const { t, i18n } = useTranslation();
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
  const [error, setError] = useState<unknown>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [models, setModels] = useState<ModelStatus[]>([]);
  const [modelsOpen, setModelsOpen] = useState(false);
  const [details, setDetails] = useState<ImageDetails | null>(null);
  const [viewer, setViewer] = useState(false);
  const [activeTurn, setActiveTurn] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ id: string; text: string } | null>(null);
  const [sources, setSources] = useState<Record<string, string>>({});
  const input = useRef<HTMLTextAreaElement>(null);
  const conversation = useRef<HTMLElement>(null);
  const followLatest = useRef(true);
  const [atBottom, setAtBottom] = useState(true);
  const busy = acting || job !== null;
  const modalOpen = viewer || settingsOpen || modelsOpen || details !== null;
  const activeImage =
    project?.images.find((image) => image.turn_id === activeTurn) ?? project?.images.at(-1);
  const actingNow = useRef(false);

  useEffect(() => {
    setActiveTurn(null);
    setViewer(false);
    setNotice((previous) => previous?.id === project?.id ? previous : null);
  }, [project?.id]);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(null), 3200);
    return () => clearTimeout(timer);
  }, [notice]);

  async function selectVersion(id: string) {
    if (!project) return;
    const image = project.images.find((image) => image.versions.includes(id));
    if (image) setActiveTurn(image.turn_id);
    await act(async () => {
      setProject(await call<Project>("select_version", project.id, id));
    });
  }

  useEffect(() => {
    function navigate(event: KeyboardEvent) {
      if (
        !project || !activeImage || event.defaultPrevented || event.isComposing ||
        event.keyCode === 229 || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey
      ) return;
      if (!["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(event.key)) return;
      const target = event.target instanceof HTMLElement ? event.target : null;
      const editable = target?.closest("input, textarea, select, [contenteditable]");
      const emptyComposer =
        editable instanceof HTMLTextAreaElement && editable === input.current && editable.value === "";
      if ((editable && !emptyComposer) || (document.querySelector(".modal") && !viewer)) return;
      if (event.key === "ArrowUp" || event.key === "ArrowDown") {
        const index = project.images.indexOf(activeImage);
        const next = index + (event.key === "ArrowUp" ? -1 : 1);
        event.preventDefault();
        if (next < 0 || next >= project.images.length) return;
        followLatest.current = false;
        setActiveTurn(project.images[next].turn_id);
      } else if (!busy && !actingNow.current && activeImage.versions.length > 1) {
        event.preventDefault();
        const versions = activeImage.versions;
        const offset = event.key === "ArrowLeft" ? -1 : 1;
        const next = (versions.indexOf(activeImage.id) + offset + versions.length) % versions.length;
        void selectVersion(versions[next]);
      }
    }
    document.addEventListener("keydown", navigate);
    return () => document.removeEventListener("keydown", navigate);
  }, [project, activeImage, busy, viewer]);

  useEffect(() => {
    let disposed = false;
    async function bootstrap() {
      try {
        const result = await call<Bootstrap>("bootstrap");
        if (disposed) return;
        await i18n.changeLanguage(result.language ?? "ko");
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
            error ?? { code: "APP_LOAD_FAILED" },
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
          if (result.error_code || result.message) setError(result);
          input.current?.focus();
          return;
        }
        setJob(result);
      } catch (error) {
        if (!disposed)
          setError(
            error ?? { code: "PROGRESS_FAILED" },
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
              error ?? { code: "IMAGE_LOAD_FAILED" },
            );
        });
    }
    return () => {
      disposed = true;
    };
  }, [project]);

  async function act(action: () => Promise<void>, clearError = true) {
    if (actingNow.current) return;
    actingNow.current = true;
    setActing(true);
    if (clearError) setError(null);
    try {
      await action();
    } catch (error) {
      setError(error ?? { code: "REQUEST_FAILED" });
    } finally {
      actingNow.current = false;
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
        error ?? { code: "CONVERSATION_LOAD_FAILED" },
      );
    }
  }
  function cancelGeneration() {
    if (!job || stopping) return;
    setStopping(true);
    void call("cancel_job", job.id).catch((error) => {
      setStopping(false);
      setError(error ?? { code: "CANCEL_FAILED" });
    });
  }

  return (
    <div className="app">
      <header inert={modalOpen}>
        <div className="brand-group">
          <span className="brand">
            <img className="brand-icon" src={appIcon} alt="" />
            moru
          </span>
          <select
            className="language-select"
            aria-label={t("language")}
            value={i18n.resolvedLanguage ?? "ko"}
            disabled={acting || !project}
            onChange={(event) => {
              const language = event.target.value;
              void act(async () => {
                const saved = await call<string>("set_language", language);
                await i18n.changeLanguage(saved);
              }, false);
            }}
          >
            <option value="ko" lang="ko">한국어</option>
            <option value="en" lang="en">English</option>
          </select>
        </div>
        <div className="header-actions">
          <select
            aria-label={t("projectHistory")}
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
                {t("project", { number: projects.length - index })} ·{" "}
                {new Date(p.created_at).toLocaleDateString(i18n.resolvedLanguage === "ko" ? "ko-KR" : "en-US")}
              </option>
            ))}
          </select>
          <button disabled={busy} onClick={() => setModelsOpen(true)}>
            <Box size={16} aria-hidden="true" /> {t("models")}
          </button>
        </div>
      </header>
      <Conversation
        project={project}
        sources={sources}
        busy={busy}
        inactive={modalOpen}
        job={job}
        scrollRef={conversation}
        followLatest={followLatest}
        onBottomChange={setAtBottom}
        activeTurnId={activeImage?.turn_id ?? null}
        onFocusImage={setActiveTurn}
        onError={setError}
        onViewImage={(turnId) => {
          setActiveTurn(turnId);
          setViewer(true);
        }}
        onShowPrompt={(id) =>
          void act(async () => {
            setDetails(await call<ImageDetails>("get_image_details", id));
          })
        }
        onFork={(id) =>
          void act(async () => {
            if (!project) return;
            setNotice(null);
            const forked = await call<Project>("fork", project.id, id);
            setProject(forked);
            setNotice({
              id: forked.id,
              text: "forked",
            });
            setProjects(await call<ProjectInfo[]>("list_projects"));
            setText("");
            input.current?.focus();
          })
        }
        onSelectVersion={(id) => { void selectVersion(id); }}
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
      {notice && (
        <div className="action-toast" key={notice.id} role="status" aria-live="polite">
          <GitBranch size={17} aria-hidden="true" />
          <span>{t(notice.text)}</span>
          <button aria-label={t("dismissNotice")}  onClick={() => setNotice(null)}>
            <X size={14} aria-hidden="true" />
          </button>
        </div>
      )}
      <footer inert={modalOpen}>
        {!atBottom && (
          <button
            className="scroll-bottom"
            aria-label={t("scrollBottom")}
            title={t("scrollBottom")}
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
        {error != null && error !== "" && (
          <div className="error-banner" role="alert">
            <span>{errorMessage(error)}</span>
            <button aria-label={t("dismissError")}  onClick={() => setError("")}>
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
            <Plus size={16} aria-hidden="true" /> {t("newProject")}
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
            aria-label={t("settings")}
            title={t("settings")}
            disabled={!settings}
            onClick={() => setSettingsOpen(true)}
          >
            <Settings2 size={20} aria-hidden="true" />
          </button>
          <textarea
            ref={input}
            aria-label={t("imageRequest")}
            placeholder={t("requestPlaceholder")}
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
            aria-label={job ? t("stop") : t("send")}
            title={job ? (stopping ? t("stopping") : t("stopGeneration")) : t("send")}
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
      {viewer && activeImage && (
        <Lightbox
          source={sources[activeImage.id] ?? null}
          imageId={activeImage.id}
          positionLabel={t("viewerPosition", { image: (project?.images.indexOf(activeImage) ?? 0) + 1, images: project?.images.length, version: activeImage.versions.indexOf(activeImage.id) + 1, versions: activeImage.versions.length })}
          onClose={() => setViewer(false)}
          onReturnFocus={() => {
            // The viewer may have moved away from the image that originally opened it.
            const selected = conversation.current?.querySelector<HTMLButtonElement>(
              ".turn.is-selected .image-button",
            );
            (selected ?? input.current)?.focus({ preventScroll: true });
          }}
        />
      )}
    </div>
  );
}
