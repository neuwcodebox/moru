(async () => {
    const call = async (name, ...args) => {
        const result = await window.pywebview.api[name](...args);
        if (!result.ok) throw new Error(result.error.message);
        return result.value;
    };
    const waitFor = predicate => predicate() ? Promise.resolve() : new Promise((resolve, reject) => {
        const timeout = setTimeout(() => { observer.disconnect(); reject(new Error('UI timeout')); }, 15000);
        const observer = new MutationObserver(() => {
            if (predicate()) { clearTimeout(timeout); observer.disconnect(); resolve(); }
        });
        observer.observe(document.body, {childList: true, subtree: true, attributes: true});
    });
    const arrow = (key, target = document) => target.dispatchEvent(new KeyboardEvent('keydown', {key, bubbles: true}));
    const turns = () => [...document.querySelectorAll('.turn')];
    const selectedText = () => document.querySelector('.turn.is-selected .user-message').textContent;
    await call('mark_stage', 'loaded');
    await waitFor(() => turns().length === 3 && document.querySelectorAll('.image-button img').length === 3);
    await Promise.all([...document.querySelectorAll('.image-button img')].map(image => image.decode()));
    await call('mark_stage', 'images decoded');
    const third = turns()[2];
    third.scrollIntoView({block: 'center'});
    third.querySelector('.image-button').dispatchEvent(new MouseEvent('mouseover', {bubbles: true}));
    await waitFor(() => third.querySelector('.prompt-content').textContent.includes('version 2'));
    // Hidden WebViews may suspend animation playback; capture the final visual state.
    document.getAnimations().filter(animation => animation.effect.getTiming().iterations !== Infinity).forEach(animation => animation.finish());
    await call('mark_stage', 'hover ready');
    await call('capture_view', 'hover');
    third.querySelector('.image-button').dispatchEvent(new MouseEvent('mouseout', {bubbles: true}));
    third.querySelector('.copy-button').click();
    await waitFor(() => third.querySelector('.copy-button.copied'));
    const imageClipboard = await call('clipboard_snapshot');
    await call('mark_stage', 'image copied');
    third.querySelectorAll('.image-actions > button')[1].click();
    await waitFor(() => document.querySelector('.prompt-editor'));
    const dialog = document.querySelector('.modal');
    const height = dialog.getBoundingClientRect().height;
    const editor = document.querySelector('.prompt-editor');
    const expectedPrompt = editor.value;
    dialog.querySelector('.copy-button').click();
    await waitFor(() => dialog.querySelector('.copy-button.copied'));
    const textClipboard = await call('clipboard_snapshot');
    await call('mark_stage', 'prompt copied');
    const stableCopyLayout = Math.abs(height - dialog.getBoundingClientRect().height) < 0.5;
    await call('capture_view', 'copy');
    arrow('Escape');
    await waitFor(() => !document.querySelector('.modal'));
    arrow('ArrowUp');
    await waitFor(() => selectedText().includes('장면 2'));
    arrow('ArrowRight');
    await waitFor(() => turns()[1].querySelector('.branch-selector span').textContent.trim() === '1 / 2');
    await waitFor(() => turns()[1].querySelector('.image-button'));
    turns()[1].querySelector('.image-button').click();
    await waitFor(() => document.querySelector('.viewer img'));
    document.querySelector('button[aria-label="확대"]').click();
    await waitFor(() => document.querySelector('.viewer-toolbar').textContent.includes('125%'));
    arrow('ArrowLeft');
    await waitFor(() => document.querySelector('.viewer-position').textContent.includes('버전 2 / 2'));
    await waitFor(() => document.querySelector('.viewer-toolbar').textContent.includes('100%'));
    arrow('ArrowUp');
    await waitFor(() => selectedText().includes('장면 1'));
    arrow('ArrowDown');
    await waitFor(() => selectedText().includes('장면 2'));
    await call('capture_view', 'viewer');
    await call('mark_stage', 'viewer navigated');
    arrow('Escape');
    await waitFor(() => !document.querySelector('.modal'));
    await waitFor(() => document.activeElement === turns()[1].querySelector('.image-button'));
    turns()[1].querySelectorAll('.image-actions > button')[3].click();
    await waitFor(() => document.querySelector('.action-toast'));
    await waitFor(() => turns().length === 2);
    await waitFor(() => document.querySelectorAll('.image-button img').length === 2);
    await Promise.all([...document.querySelectorAll('.image-button img')].map(image => image.decode()));
    document.getAnimations().filter(animation => animation.effect.getTiming().iterations !== Infinity).forEach(animation => animation.finish());
    await call('capture_view', 'fork');
    const forked = await call('bootstrap');
    const original = await call('get_project', 'ui-project');
    return {ok: true, imageClipboard, textClipboardMatches: textClipboard.text === expectedPrompt,
        stableCopyLayout, hoverPrompt: true, keyboardConversation: true, keyboardViewer: true,
        forkFeedback: !!document.querySelector('.action-toast'), forkedRows: forked.project.images.length,
        originalRows: original.images.length, newSession: forked.project.id !== original.id,
        logo: !!document.querySelector('.brand-icon').naturalWidth};
})().catch(error => ({ok: false, error: String(error)}))
