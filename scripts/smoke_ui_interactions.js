(async () => {
    const call = async (name, ...args) => {
        const result = await window.pywebview.api[name](...args);
        if (!result.ok) throw new Error(result.error.message);
        return result.value;
    };
    const waitFor = predicate => predicate() ? Promise.resolve() : new Promise((resolve, reject) => {
        const timeout = setTimeout(() => { observer.disconnect(); reject(new Error(`UI timeout: ${predicate}`)); }, 15000);
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
    const assertConversationScroll = () => {
        const page = document.scrollingElement;
        const conversation = document.querySelector('.conversation');
        if (page.scrollHeight > page.clientHeight || page.scrollWidth > page.clientWidth)
            throw new Error(`The outer page overflows the desktop viewport: ${JSON.stringify({
                page: [page.scrollWidth, page.scrollHeight, page.clientWidth, page.clientHeight],
                viewport: [innerWidth, innerHeight],
            })}`);
        if (conversation.scrollHeight <= conversation.clientHeight)
            throw new Error('Long conversation has no scrollable area');
        conversation.scrollTop = 0;
        conversation.scrollTop = conversation.scrollHeight;
        if (conversation.scrollTop <= 0) throw new Error('Conversation cannot scroll');
        const footer = document.querySelector('footer').getBoundingClientRect();
        if (footer.bottom > innerHeight + 1 || footer.top < 0)
            throw new Error('Composer is outside the desktop viewport');
        return true;
    };
    const singleConversationScroll = assertConversationScroll();
    const wheelInside = async (element, deltaY) => {
        const rect = element.getBoundingClientRect();
        await call('wheel_at', rect.right - 20, rect.top + rect.height / 2, deltaY);
    };
    const waitScroll = (element, predicate) => predicate() ? Promise.resolve() : new Promise((resolve, reject) => {
        const timeout = setTimeout(() => { element.removeEventListener('scroll', check); reject(new Error('Scroll timeout')); }, 15000);
        function check() {
            if (predicate()) { clearTimeout(timeout); element.removeEventListener('scroll', check); resolve(); }
        }
        element.addEventListener('scroll', check);
    });
    const checkModalScroll = async (modal, screenshot) => {
        const conversation = document.querySelector('.conversation');
        const before = conversation.scrollTop;
        if (!conversation.inert || getComputedStyle(conversation).overflowY !== 'hidden')
            throw new Error('Background conversation is not locked');
        if (modal.scrollHeight <= modal.clientHeight) throw new Error('Expected a scrollable dialog');
        modal.scrollTop = 0;
        const scrolled = waitScroll(modal, () => modal.scrollTop > 0);
        await wheelInside(modal, 240);
        await scrolled;
        modal.scrollTop = modal.scrollHeight;
        await wheelInside(modal, 240);
        await call('wheel_at', 10, innerHeight / 2, 240);
        await call('capture_view', screenshot);
        if (conversation.scrollTop !== before) throw new Error('Dialog wheel scrolled the background');
        return true;
    };
    const centeredPrompt = (container, content) => {
        const frame = container.getBoundingClientRect();
        const text = content.getBoundingClientRect();
        if (Math.abs((text.top + text.bottom) - (frame.top + frame.bottom)) > 2)
            throw new Error('Prompt is not vertically centered');
        if (text.top < frame.top || text.bottom > frame.bottom)
            throw new Error('Prompt extends beyond its image frame');
        return true;
    };
    const first = turns()[0];
    first.scrollIntoView({block: 'center'});
    first.querySelector('.image-button').dispatchEvent(new MouseEvent('mouseover', {bubbles: true}));
    await waitFor(() => first.querySelector('.prompt-content').textContent.includes('scene 1'));
    const centeredHoverPrompt = centeredPrompt(first.querySelector('.image-button'), first.querySelector('.prompt-text'));
    first.querySelector('.image-button').dispatchEvent(new MouseEvent('mouseout', {bubbles: true}));
    const third = turns()[2];
    const imageFrame = third.querySelector('.image-button').getBoundingClientRect();
    third.scrollIntoView({block: 'center'});
    third.querySelector('.image-button').dispatchEvent(new MouseEvent('mouseover', {bubbles: true}));
    await waitFor(() => third.querySelector('.prompt-content').textContent.includes('version 2'));
    const longPrompt = third.querySelector('.prompt-content');
    if (longPrompt.scrollHeight <= longPrompt.clientHeight) throw new Error('Long hover prompt cannot scroll');
    const hoverFrame = third.querySelector('.image-button').getBoundingClientRect();
    if (imageFrame.width !== hoverFrame.width || imageFrame.height !== hoverFrame.height)
        throw new Error('Hover prompt expanded the image');
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
    const conversationBeforePromptScroll = document.querySelector('.conversation').scrollTop;
    editor.scrollTop = editor.scrollHeight;
    await wheelInside(editor, 240);
    await call('capture_view', 'copy');
    const promptDialogScrollIsolated = document.querySelector('.conversation').scrollTop === conversationBeforePromptScroll;
    if (!promptDialogScrollIsolated) throw new Error('Prompt editor wheel scrolled the background');
    arrow('Escape');
    await waitFor(() => !document.querySelector('.modal'));
    arrow('ArrowUp');
    await waitFor(() => selectedText().includes('장면 2'));
    arrow('ArrowRight');
    await waitFor(() => turns()[1].querySelector('.branch-selector span').textContent.trim() === '1 / 2');
    await waitFor(() => turns()[1].querySelector('.image-button'));
    turns()[1].querySelector('.image-button').click();
    await waitFor(() => document.querySelector('.viewer img'));
    const conversation = document.querySelector('.conversation');
    const backgroundScroll = conversation.scrollTop;
    const viewerFrame = document.querySelector('.viewer').getBoundingClientRect();
    await call('wheel_at', viewerFrame.x + viewerFrame.width / 2, viewerFrame.y + viewerFrame.height / 2, -120);
    await waitFor(() => document.querySelector('.viewer-toolbar').textContent.includes('110%'));
    if (conversation.scrollTop !== backgroundScroll) throw new Error('Viewer wheel scrolled the background');
    document.querySelector('button[aria-label="화면 맞춤"]').click();
    await waitFor(() => document.querySelector('.viewer-toolbar').textContent.includes('100%'));
    document.querySelector('button[aria-label="확대"]').click();
    await waitFor(() => document.querySelector('.viewer-toolbar').textContent.includes('125%'));
    arrow('ArrowLeft');
    await waitFor(() => document.querySelector('.viewer-position').textContent.includes('버전 2 / 2'));
    await waitFor(() => document.querySelector('.viewer-toolbar').textContent.includes('100%'));
    arrow('ArrowUp');
    await waitFor(() => selectedText().includes('장면 1'));
    arrow('ArrowDown');
    await waitFor(() => selectedText().includes('장면 2'));
    if (conversation.scrollTop !== backgroundScroll) throw new Error('Viewer navigation scrolled the background');
    await call('capture_view', 'viewer');
    await call('mark_stage', 'viewer navigated');
    arrow('Escape');
    await waitFor(() => !document.querySelector('.modal'));
    await waitFor(() => document.activeElement === turns()[1].querySelector('.image-button'));
    if (turns()[1].querySelector('.image-prompt-overlay').getAttribute('aria-hidden') !== 'true')
        throw new Error('Closing the viewer revealed a hover prompt');
    conversation.scrollTop = 0;
    document.querySelector('button[aria-label="생성 설정"]').click();
    await waitFor(() => document.querySelector('.advanced-settings'));
    document.querySelector('.advanced-settings').open = true;
    const settingsScrollIsolated = await checkModalScroll(document.querySelector('.modal'), 'settings');
    arrow('Escape');
    await waitFor(() => !document.querySelector('.modal'));
    if (conversation.scrollTop !== 0) throw new Error(`Closing settings moved the reading position to ${conversation.scrollTop}`);
    [...document.querySelectorAll('header button')].find(button => button.textContent.includes('모델 설정')).click();
    await waitFor(() => document.querySelectorAll('.model-row').length === 5);
    const modelsScrollIsolated = await checkModalScroll(document.querySelector('.modal'), 'models');
    arrow('Escape');
    await waitFor(() => !document.querySelector('.modal'));
    if (conversation.scrollTop !== 0) throw new Error('Closing model settings moved the reading position');
    await call('mark_stage', 'all dialog scrolls isolated');
    turns()[1].querySelectorAll('.image-actions > button')[3].click();
    await waitFor(() => document.querySelector('.action-toast'));
    await waitFor(() => turns().length === 2);
    await waitFor(() => document.querySelectorAll('.image-button img').length === 2);
    await Promise.all([...document.querySelectorAll('.image-button img')].map(image => image.decode()));
    document.getAnimations().filter(animation => animation.effect.getTiming().iterations !== Infinity).forEach(animation => animation.finish());
    await call('capture_view', 'fork');
    const forked = await call('bootstrap');
    const original = await call('get_project', 'ui-project');
    assertConversationScroll();
    const forkFeedback = !!document.querySelector('.action-toast');
    await call('update_settings', {model_id: 'anima-turbo-v1.1', width: 832, height: 1216});
    const composer = document.querySelector('.composer textarea');
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(composer, '긴 프롬프트 화면 검증');
    composer.dispatchEvent(new Event('input', {bubbles: true}));
    document.querySelector('.send-button').click();
    await waitFor(() => document.querySelector('.generation-placeholder .prompt-text'));
    const placeholder = document.querySelector('.generation-placeholder');
    const requestedFrame = placeholder.getBoundingClientRect();
    if (Math.abs(requestedFrame.width / requestedFrame.height - 832 / 1216) > 0.01)
        throw new Error('Placeholder does not match the requested image ratio');
    const centeredGenerationPrompt = centeredPrompt(placeholder.querySelector('.generation-canvas'), placeholder.querySelector('.prompt-text'));
    await call('set_preview_prompt', 'snowy street, ' + 'detailed scenery, '.repeat(500));
    await waitFor(() => placeholder.querySelector('.prompt-content').textContent.length > 5000);
    const finalFrame = placeholder.getBoundingClientRect();
    const livePrompt = placeholder.querySelector('.prompt-content');
    if (finalFrame.width !== requestedFrame.width || finalFrame.height !== requestedFrame.height)
        throw new Error('Streaming prompt expanded the placeholder');
    if (livePrompt.scrollHeight <= livePrompt.clientHeight) throw new Error('Long streaming prompt cannot scroll');
    centeredPrompt(placeholder.querySelector('.generation-canvas'), placeholder.querySelector('.prompt-text'));
    await call('capture_view', 'generation');
    await call('set_preview_prompt', null);
    await waitFor(() => !document.querySelector('.generation-placeholder'));
    return {ok: true, viewport: [innerWidth, innerHeight], imageClipboard, textClipboardMatches: textClipboard.text === expectedPrompt,
        stableCopyLayout, singleConversationScroll, centeredHoverPrompt, centeredGenerationPrompt,
        boundedPromptScroll: true, requestedPlaceholderRatio: true, viewerScrollIsolated: true,
        settingsScrollIsolated, modelsScrollIsolated, promptDialogScrollIsolated,
        hoverResetAfterViewer: true, hoverPrompt: true, keyboardConversation: true, keyboardViewer: true,
        forkFeedback, forkedRows: forked.project.images.length,
        originalRows: original.images.length, newSession: forked.project.id !== original.id,
        logo: !!document.querySelector('.brand-icon').naturalWidth};
})().catch(error => ({ok: false, error: String(error)}))
