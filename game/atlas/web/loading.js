// Installed before the large catalog script, so the first paint has feedback.
(() => {
    const cards = document.getElementById('cards');
    const status = document.getElementById('atlas-loading-status');
    let rendered = false;
    let scheduled = false;
    let failedToRender = false;

    function update() {
        scheduled = false;
        if (!rendered || failedToRender) return;
        let pending = 0;
        for (const stage of cards.querySelectorAll('.stage')) {
            const images = [...stage.querySelectorAll('img[src]')];
            const waiting = images.some(image => !image.complete);
            const failed = !waiting && images.some(image => !image.naturalWidth);
            stage.classList.toggle('atlas-image-loading', waiting);
            stage.classList.toggle('atlas-image-error', failed);
            stage.setAttribute('aria-busy', String(waiting));
            if (waiting) pending++;
        }
        cards.setAttribute('aria-busy', String(pending > 0));
        status.hidden = pending === 0;
        if (pending) status.textContent = 'Loading item images…';
    }

    function schedule() {
        if (scheduled) return;
        scheduled = true;
        requestAnimationFrame(update);
    }

    // Observe replacement cards, pagination, original-frame changes and the
    // animation toggle. Cached images need the same check as network images.
    new MutationObserver(records => {
        if (records.some(record => record.type === 'childList' && record.target === cards)) {
            rendered = true;
        }
        schedule();
    }).observe(cards, {childList: true, subtree: true, attributes: true, attributeFilter: ['src']});
    cards.addEventListener('load', schedule, true);
    cards.addEventListener('error', schedule, true);
    document.addEventListener('DOMContentLoaded', () => {
        if (rendered) return;
        failedToRender = true;
        cards.replaceChildren();
        status.classList.add('atlas-loading-error');
        status.textContent = 'The item cards could not load. Please reload the page.';
        // Disconnect the initial placeholder from normal loading completion.
        rendered = true;
        status.hidden = false;
        cards.setAttribute('aria-busy', 'false');
    }, {once: true});
})();
