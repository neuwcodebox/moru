import { useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { ExternalLink, LogOut, RefreshCw, UserPlus } from "lucide-react";
import { call } from "./api";
import type { ChatGPTModel, ChatGPTStatus } from "./api";
import { errorMessage } from "./errorMessages";

export default function ChatGPTAccount({ status, model, disabled = false, onStatus, onModel }: {
  status: ChatGPTStatus | null;
  model: string;
  disabled?: boolean;
  onStatus: (status: ChatGPTStatus) => void;
  onModel: (model: string) => void | Promise<void>;
}) {
  const { t } = useTranslation("dialogs");
  const [models, setModels] = useState<ChatGPTModel[]>([]);
  const [acting, setActing] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [refresh, setRefresh] = useState(0);
  const [loadingModels, setLoadingModels] = useState(false);
  const [catalogLoaded, setCatalogLoaded] = useState(false);
  const modelFieldId = useId();
  const accountFieldId = useId();
  const waiting = status?.login_state === "waiting";
  const ready = status?.connected && status.plan_enabled;
  const modelAvailable = models.some((choice) => choice.slug === model);

  useEffect(() => {
    let disposed = false;
    setModels([]);
    setCatalogLoaded(false);
    if (!ready) return;
    setLoadingModels(true);
    void call<ChatGPTModel[]>("get_chatgpt_models").then((choices) => {
      if (disposed) return;
      setModels(choices);
      setCatalogLoaded(true);
      setError(null);
    }).catch((cause) => { if (!disposed) setError(cause); })
      .finally(() => { if (!disposed) setLoadingModels(false); });
    return () => { disposed = true; };
  }, [status?.active_account, ready, refresh]);

  useEffect(() => {
    if (!waiting) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const fresh = await call<ChatGPTStatus>("get_chatgpt_status");
        if (disposed) return;
        onStatus(fresh);
        if (fresh.login_state !== "waiting") {
          if (fresh.error_code) setError({ code: fresh.error_code });
          return;
        }
      } catch (cause) { if (!disposed) setError(cause); }
      if (!disposed) timer = setTimeout(poll, 500);
    }
    void poll();
    return () => { disposed = true; clearTimeout(timer); };
  }, [waiting, onStatus]);

  async function action(method: string, ...args: unknown[]) {
    setActing(true);
    setError(null);
    try {
      onStatus(await call<ChatGPTStatus>(method, ...args));
    } catch (cause) { setError(cause); }
    finally { setActing(false); }
  }

  async function selectModel(model: string) {
    setActing(true);
    setError(null);
    try { await onModel(model); }
    catch (cause) { setError(cause); }
    finally { setActing(false); }
  }

  return <section className="chatgpt-account" aria-label="ChatGPT">
    <div className="account-heading">
      {!!status?.accounts.length && <label htmlFor={accountFieldId}>{t("chatgpt.account")}</label>}
      <a href="https://chatgpt.com/settings/usage" target="_blank" rel="noopener noreferrer">
        {t("chatgpt.manageUsage")} <ExternalLink size={14} aria-hidden="true" />
      </a>
    </div>
    {status?.accounts.length ? <select id={accountFieldId} value={status.active_account ?? ""}
        disabled={disabled || acting || waiting}
        onChange={(event) => void action("select_chatgpt_account", event.target.value)}>
        {status.accounts.map((account, index) => <option key={account.id} value={account.id}>
          {account.email ?? t("chatgpt.account")} · {index + 1}
        </option>)}
      </select> : null}
    <p role="status">{waiting ? t("chatgpt.waiting") : status?.connected
      ? t("chatgpt.connected") : t("chatgpt.disconnected")}</p>
    <div className="model-actions">
      {!status?.connected || !status.plan_enabled ? <button type="button" disabled={disabled || acting || waiting}
        onClick={() => void action("login_chatgpt", status?.active_account ?? null)}>
        {t(status?.connected ? "chatgpt.grantPermission" : status?.active_account
          ? "chatgpt.signInAgain" : "chatgpt.signIn")}
      </button> : null}
      {status?.accounts.length ? <button type="button" disabled={disabled || acting || waiting}
        onClick={() => void action("login_chatgpt")}>
        <UserPlus size={16} aria-hidden="true" /> {t("chatgpt.addAccount")}
      </button> : null}
      {waiting ? <button type="button" disabled={acting}
        onClick={() => void action("cancel_chatgpt_login")}>{t("chatgpt.cancel")}</button> : null}
      {status?.connected && <button type="button" disabled={disabled || acting || waiting}
        onClick={() => void action("logout_chatgpt")}>
        <LogOut size={16} aria-hidden="true" /> {t("chatgpt.logout")}
      </button>}
    </div>
    {ready && <>
      <label htmlFor={modelFieldId}>{t("chatgpt.model")}</label>
      <div className="model-choice-row">
        <select id={modelFieldId} value={model} disabled={disabled || acting || models.length === 0 || loadingModels}
          onChange={(event) => void selectModel(event.target.value)}>
          <option value="" disabled>{t("chatgpt.selectModel")}</option>
          {model && !modelAvailable &&
            <option value={model} disabled>{model}</option>}
          {models.map((choice) => <option key={choice.slug} value={choice.slug}>
            {choice.display_name}
          </option>)}
        </select>
        <button type="button" className="model-refresh" aria-label={t("chatgpt.refreshModels")}
          title={t("chatgpt.refreshModels")} disabled={disabled || acting || loadingModels}
          onClick={() => setRefresh((value) => value + 1)}>
          <RefreshCw size={18} className={loadingModels ? "spinner" : undefined} aria-hidden="true" />
        </button>
      </div>
      {catalogLoaded && model && !modelAvailable &&
        <p role="alert">{t("chatgpt.modelUnavailable")}</p>}
    </>}
    {status?.connected && !status.plan_enabled && <p role="alert">{t("chatgpt.noPermission")}</p>}
    {status?.revocation_confirmed === false && <p role="alert">{t("chatgpt.revocationUnconfirmed")}</p>}
    <details className="account-notes">
      <summary>{t("chatgpt.usageNotes")}</summary>
      <p className="hint">{t("chatgpt.privacy")}</p>
      <p className="hint">{t("chatgpt.policy")}</p>
    </details>
    {error != null && <p role="alert">{errorMessage(error, "CHATGPT_UNAVAILABLE")}</p>}
    {error == null && status?.error_code && <p role="alert">{errorMessage(status)}</p>}
  </section>;
}
