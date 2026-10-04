"""Opt-in packaged GPU/UI verification using a synthetic request and isolated data."""

import json
from pathlib import Path
from threading import Event


def verify_window(window, report_path: Path, ui_only=False):
    completed = Event()
    results = []
    report = {"ok": False}
    previous_clipboard = []
    clipboard_sentinel = "Moru clipboard smoke"
    try:
        if not window.events.loaded.wait(30):
            raise RuntimeError("WebView2 did not load")
        if ui_only:
            from System import Action
            from System.Windows.Forms import Clipboard

            window.native.Invoke(
                Action(lambda: previous_clipboard.append(Clipboard.GetDataObject()))
            )
        window.evaluate_js(
            """
            (async () => {
                const api = window.pywebview.api;
                const call = async (name, ...args) => {
                    const response = await api[name](...args);
                    if (!response.ok) throw new Error(response.error.code);
                    return response.value;
                };
                await new Promise(resolve => {
                    const ready = () => {
                        const input = document.querySelector('textarea');
                        return input && !input.disabled;
                    };
                    if (ready()) return resolve();
                    const observer = new MutationObserver(() => {
                        if (ready()) { observer.disconnect(); resolve(); }
                    });
                    observer.observe(document.body,
                        {childList: true, subtree: true, attributes: true});
                });
                const settings = await call('get_settings');
                const promptSettings = await call('get_prompt_settings');
                const waitFor = async (predicate) => {
                    if (predicate()) return;
                    await new Promise(resolve => {
                        const observer = new MutationObserver(() => {
                            if (predicate()) { observer.disconnect(); resolve(); }
                        });
                        observer.observe(document.body,
                            {childList: true, subtree: true, attributes: true});
                    });
                };
                const setValue = async (input, value) => {
                    const prototype = input instanceof HTMLTextAreaElement
                        ? HTMLTextAreaElement.prototype
                        : input instanceof HTMLSelectElement
                            ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
                    Object.getOwnPropertyDescriptor(prototype, 'value').set.call(input, value);
                    input.dispatchEvent(new Event(
                        input instanceof HTMLSelectElement ? 'change' : 'input', {bubbles: true}));
                    await new Promise(resolve => setTimeout(resolve, 0));
                };
                if (__UI_ONLY__) {
                    document.querySelector('.settings-button').click();
                    await waitFor(() => document.querySelector('.advanced-settings'));
                    document.querySelector('.advanced-settings summary').click();
                    const controls = document.querySelectorAll('.advanced-settings input');
                    if (controls[0].value !== String(promptSettings.context_size)
                        || controls[1].value !== String(promptSettings.max_tokens)
                        || controls[2].value !== '4' || !controls[3].checked
                        || document.querySelector('.advanced-settings select').value
                            !== promptSettings.reasoning_level)
                        throw new Error('Incorrect prompt defaults');
                    await setValue(controls[0], '8192');
                    await setValue(controls[1], '4096');
                    await setValue(document.querySelector('.advanced-settings select'), 'high');
                    await new Promise(resolve => setTimeout(resolve, 0));
                    document.querySelector('.advanced-settings').closest('form').requestSubmit();
                    await waitFor(() => !document.querySelector('.advanced-settings'));
                    const saved = await call('get_prompt_settings');
                    if (saved.context_size !== 8192 || saved.max_tokens !== 4096
                        || saved.thinking !== true || saved.reasoning_level !== 'high')
                        throw new Error('Prompt settings not saved');
                    await call('update_settings', settings, promptSettings);
                    await call('copy_prompt', 'Moru clipboard smoke');
                    return {ok: true, title: document.title, defaults: settings,
                        prompt_defaults: promptSettings, saved_prompt_settings: saved,
                        ui_only: true};
                }
                const originalSubmit = api.submit_request;
                let accepted;
                const submission = new Promise((resolve, reject) => {
                    accepted = async (...args) => {
                        try {
                            const response = await originalSubmit(...args);
                            if (response.ok) resolve(response.value);
                            else reject(new Error(response.error.code));
                            return response;
                        } catch (error) { reject(error); throw error; }
                    };
                });
                let job;
                try {
                    api.submit_request = accepted;
                    await setValue(document.querySelector('.composer textarea'),
                        '은발 소녀가 편의점 앞에서 컵라면을 먹는 장면');
                    document.querySelector('.composer').requestSubmit();
                    job = await submission;
                } finally { api.submit_request = originalSubmit; }
                let result;
                do {
                    result = await call('get_job', job.id);
                    if (['failed', 'cancelled'].includes(result.state))
                        throw new Error(result.error_code);
                    if (result.state !== 'completed')
                        await new Promise(resolve => setTimeout(resolve, 250));
                } while (result.state !== 'completed');
                await waitFor(() => document.querySelector('.image-button img')
                    && !document.querySelector('.composer textarea').disabled);
                const updated = await call('get_project', job.project_id);
                const image = updated.images[0];
                const details = await call('get_image_details', image.id);
                const decoded = document.querySelector('.image-button img');
                await decoded.decode();
                return {ok: true, title: document.title,
                    defaults: settings, prompt_defaults: promptSettings, image_id: image.id,
                    prompt_written: details.prompt.length > 0,
                    conversation_image_visible: true,
                    actual_seed: details.settings.seed,
                    image_size: [decoded.naturalWidth, decoded.naturalHeight]};
            })().catch(error => ({ok: false, error: String(error.message)}))
            """.replace("__UI_ONLY__", "true" if ui_only else "false"),
            callback=lambda result: (results.append(result), completed.set()),
        )
        if not completed.wait(600):
            raise RuntimeError("Packaged generation did not finish")
        report = results[0]
        if ui_only and report.get("ok"):
            verified = []
            window.native.Invoke(
                Action(lambda: verified.append(Clipboard.GetText() == clipboard_sentinel))
            )
            report["clipboard_copied"] = verified[0]
            report["ok"] = verified[0]
    except Exception as exc:
        report = {"ok": False, "error": str(exc)}
    finally:
        if previous_clipboard:

            def restore_clipboard():
                # Preserve any clipboard update the user made during this smoke check.
                if Clipboard.GetText() == clipboard_sentinel:
                    if previous_clipboard[0] is None:
                        Clipboard.Clear()
                    else:
                        Clipboard.SetDataObject(previous_clipboard[0], True)

            window.native.Invoke(Action(restore_clipboard))
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        window.destroy()
