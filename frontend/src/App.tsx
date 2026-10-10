import { errorMessage } from "./errorMessages";
import { useTranslation } from "react-i18next";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
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
  ChatGPTStatus,
  ImageDetails,
  Job,
  ModelStatus,
  Project,
  ProjectInfo,
  PromptSettings,
  PromptSource,
  ImageModel,
  Settings,
} from "./api";
import Lightbox from "./Lightbox";
import PromptDialog from "./PromptDialog";
import SourcesDialog from "./SourcesDialog";
import SettingsDialog from "./SettingsDialog";
import ModelsDialog from "./ModelsDialog";
import Conversation from "./Conversation";
import Modal from "./Modal";
import { canUseChatGPT } from "./promptAvailability";

export default function App() {
  const { t, i18n } = useTranslation();
  const [project, setProject] = useState<Project | null>(null);
  const [projects, setProjects] = useState<ProjectInfo[]>([]);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [imageModels, setImageModels] = useState<ImageModel[]>([]);
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
  const [modelsKnown, setModelsKnown] = useState(false);
  const [modelsOpen, setModelsOpen] = useState(false);
  const [chatgpt, setChatgpt] = useState<ChatGPTStatus | null>(null);
  const sourceTrigger = useRef<HTMLElement | null>(null);
  const [promptSources, setPromptSources] = useState<PromptSource[] | null>(null);
  const [details, setDetails] = useState<ImageDetails | null>(null);
  const [viewer, setViewer] = useState(false);
  const [activeTurn, setActiveTurn] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ id: string; text: string } | null>(null);
  const [sources, setSources] = useState<Record<string, string>>({});
  const input = useRef<HTMLTextAreaElement>(null);
  const conversation = useRef<HTMLElement>(null);
  const composerArea = useRef<HTMLElement>(null);
  const followLatest = useRef(true);
  const [atBottom, setAtBottom] = useState(true);
  const busy = acting || job !== null;
  const promptReady = promptSettings?.provider === "chatgpt"
    ? canUseChatGPT(chatgpt, promptSettings.chatgpt_model)
    : !modelsKnown || !!models.find((model) => model.id === "prompt")?.available;
  const modalOpen = viewer || settingsOpen || modelsOpen || details !== null || promptSources !== null || !!chatgpt?.welcome_pending;
  const activeImage =
    project?.images.find((image) => image.turn_id === activeTurn) ?? project?.images.at(-1);
  const actingNow = useRef(false);

  useLayoutEffect(() => {
    const element = composerArea.current;
    if (!element) return;
    const measure = () => conversation.current?.style.setProperty(
      "--composer-height", `${element.getBoundingClientRect().height}px`,
    );
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    setActiveTurn(null);
    setViewer(false);
    setPromptSources(null);
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
      let language = "en";
      try {
        const saved = await call<string>("get_language");
        if (saved === "ko" || saved === "en") language = saved;
      } catch {
        // Preference access can fail too; use English for the remaining startup path.
      }
      if (disposed) return;
      await i18n.changeLanguage(language);
      if (disposed) return;
      try {
        const result = await call<Bootstrap>("bootstrap");
        if (disposed) return;
        await i18n.changeLanguage(result.language === "ko" ? "ko" : "en");
        if (disposed) return;
        setProject(result.project);
        setProjects(result.projects);
        setSettings(result.settings);
        setImageModels(result.image_models);
        setPromptSettings(result.prompt_settings);
        setError("");
        setModels(result.models ?? []);
        setModelsKnown(result.models !== undefined);
        setChatgpt(result.chatgpt ?? null);
        const selected = result.image_models.find((model) => model.id === result.settings.model_id);
        const required = [...(selected?.asset_ids ?? [])];
        const promptReady = result.prompt_settings.provider === "chatgpt"
          ? canUseChatGPT(result.chatgpt, result.prompt_settings.chatgpt_model)
          : result.models?.find((model) => model.id === "prompt")?.available;
        if (
          result.models && (!promptReady || required.some((id) => !result.models?.find((model) => model.id === id)?.available))
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
    if (!project || busy || !promptReady || !text.trim()) return;
    await act(async () => {
      scrollToBottom();
      await startGeneration("submit_request", project.id, text);
      setText("");
    });
  }
  function scrollToBottom() {
    followLatest.current = true;
    conversation.current?.scrollTo({
      top: conversation.current.scrollHeight,
      behavior: "instant",
    });
    setAtBottom(true);
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
          <span className="brand">moru</span>
          <select
            className="language-select"
            aria-label={t("language")}
            value={i18n.resolvedLanguage ?? "en"}
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
        onShowSources={(id, trigger) => {
          // Loading disables menu buttons; remember the opener before native focus is lost.
          sourceTrigger.current = trigger;
          void act(async () => {
            setPromptSources(await call<PromptSource[]>("get_image_sources", id));
          });
        }}
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
      <footer ref={composerArea} inert={modalOpen}>
        {!atBottom && (
          <button
            className="scroll-bottom"
            aria-label={t("scrollBottom")}
            title={t("scrollBottom")}
            onClick={scrollToBottom}
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
          {promptSettings && <label className="prompt-provider-select">
            <span className="sr-only">{t("dialogs:chatgpt.provider")}</span>
            <select aria-label={t("dialogs:chatgpt.provider")}
              value={promptSettings.provider ?? "local"} disabled={busy}
              onChange={(event) => {
                const provider = event.target.value;
                void act(async () => setPromptSettings(await call<PromptSettings>("select_prompt_provider", provider)));
              }}>
              <option value="local" disabled={models.length > 0 && !models.find((model) => model.id === "prompt")?.available}>
                {t("dialogs:chatgpt.local")}
              </option>
              <option value="chatgpt" disabled={!canUseChatGPT(chatgpt, promptSettings.chatgpt_model)}>
                ChatGPT
              </option>
            </select>
          </label>}
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
            disabled={job ? stopping : busy || !promptReady || !text.trim() || !project}
          >
            {job ? (
              <Square size={17} fill="currentColor" aria-hidden="true" />
            ) : (
              <ArrowUp size={22} aria-hidden="true" />
            )}
          </button>
        </form>
      </footer>
      {settingsOpen && settings && promptSettings && !chatgpt?.welcome_pending && (
        <SettingsDialog
          settings={settings}
          imageModels={imageModels}
          promptSettings={promptSettings}
          chatgpt={chatgpt}
          localReady={!!models.find((model) => model.id === "prompt")?.available}
          onClose={() => setSettingsOpen(false)}
          onSave={async (draft, promptDraft) => {
            setSettings(
              await call<Settings>("update_settings", draft, promptDraft),
            );
            setPromptSettings(promptDraft);
          }}
        />
      )}
      {modelsOpen && settings && (
        <ModelsDialog
          initial={models}
          imageModels={imageModels}
          initialModelId={settings.model_id}
          onUpdate={setModels}
          onClose={() => setModelsOpen(false)}
          chatgpt={chatgpt}
          suspended={!!chatgpt?.welcome_pending}
          promptSettings={promptSettings ?? undefined}
          onChatGPTStatus={setChatgpt}
          onConfigurePrompt={async (values) => {
            const saved = await call<PromptSettings>("configure_prompt_writer", values);
            setPromptSettings(saved);
            return saved;
          }}
        />
      )}
      {chatgpt?.welcome_pending && <Modal title={t("dialogs:chatgpt.welcomeTitle")}
        onClose={() => void act(async () => setChatgpt(await call<ChatGPTStatus>("dismiss_chatgpt_welcome")))}>
        <p>{t("dialogs:chatgpt.welcomeBody")}</p>
        <a href="https://chatgpt.com/settings/usage" target="_blank" rel="noopener noreferrer">
          {t("dialogs:chatgpt.manageUsage")}
        </a>
        <div className="modal-actions"><button type="button" disabled={acting}
          onClick={() => void act(async () => setChatgpt(await call<ChatGPTStatus>("dismiss_chatgpt_welcome")))}>
          {t("dialogs:chatgpt.gotIt")}
        </button></div>
      </Modal>}
      {promptSources !== null && (
        <SourcesDialog sources={promptSources} onClose={() => setPromptSources(null)}
          onReturnFocus={() => sourceTrigger.current?.focus({ preventScroll: true })} />
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
