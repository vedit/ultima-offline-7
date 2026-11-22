(() => {
    for (const figure of document.querySelectorAll('.loadable')) {
        const img = figure.querySelector('img');
        const update = () => {
            figure.classList.toggle('is-loading', !img.complete);
            figure.classList.toggle('load-error', img.complete && !img.naturalWidth);
            figure.setAttribute('aria-busy', String(!img.complete));
        };
        img.addEventListener('load', update);
        img.addEventListener('error', update);
        new MutationObserver(update).observe(img, {attributes:true, attributeFilter:['src']});
        update();
    }
    const image = document.getElementById('comparison-image');
    const caption = document.getElementById('comparison-caption');
    for (const button of document.querySelectorAll('[data-view]')) {
        button.addEventListener('click', () => {
            const original = button.dataset.view === 'original';
            image.src = original ? 'site/fellowship-interior-u7.png' : 'site/fellowship-interior-uo7.png';
            image.alt = original ? 'The Fellowship hall interior in original Ultima VII.' : 'Vedit in the Fellowship hall with the paperdoll and full character status sheet open.';
            caption.textContent = original ? 'The original Ultima VII room. Different camera, familiar details.' : 'Vedit in the Fellowship hall with the character status sheet open.';
            for (const sibling of document.querySelectorAll('[data-view]')) sibling.setAttribute('aria-pressed', String(sibling === button));
        });
    }
    const dialog = document.getElementById('screenshot-dialog');
    const full = document.getElementById('screenshot-image');
    const comparison = document.getElementById('screenshot-comparison');
    const stage = document.getElementById('compare-stage');
    const slider = document.getElementById('compare-slider');
    const originalImage = document.getElementById('compare-original');
    const currentImage = document.getElementById('compare-current');
    const loading = document.getElementById('compare-loading');
    const error = document.getElementById('compare-error');
    const pairs = {
        'barn-overview': {title: 'The murder in Trinsic — Christopher and Inamo', description: 'The barn murder scene with both victims visible', currentAlt: "Christopher and Inamo in the Trinsic barn, with Vedit's paperdoll and compact health and mana bars."},
        'fellowship-interior': {title: 'Inside the Fellowship — Trinsic', description: 'The Fellowship hall interior', currentAlt: 'Vedit in the Fellowship hall with the paperdoll and full character status sheet open.'},
        'guardian-dream': {
            title: 'The Guardian — original opening and playable dream',
            originalAlt: 'The Guardian speaking against blue static in the original Ultima VII DOS opening cutscene.',
            currentAlt: 'The Guardian speaks above the sleeping Avatar in the Ultima Offline 7 in-engine dream.',
            help: 'Drag the divider, or use the arrow keys. Original opening cutscene and our playable dream adaptation.'
        }
    };
    let activePair = 'barn-overview';
    let request = 0;
    function updateSplit() {
        stage.style.setProperty('--split', `${slider.value}%`);
        slider.setAttribute('aria-valuetext', `${slider.value}% Ultima Offline 7; ${100 - slider.value}% original Ultima VII`);
    }
    async function showPair(id) {
        const pair = pairs[id];
        if (!pair) return;
        activePair = id;
        const currentRequest = ++request;
        full.hidden = true;
        comparison.hidden = false;
        slider.value = 50;
        updateSplit();
        stage.setAttribute('aria-busy', 'true');
        loading.hidden = false;
        error.hidden = true;
        for (const button of document.querySelectorAll('[data-pair]')) button.setAttribute('aria-pressed', String(button.dataset.pair === id));
        originalImage.src = `site/${id}-u7.png`;
        originalImage.alt = pair.originalAlt || `${pair.description} in the original Ultima VII renderer.`;
        currentImage.src = `site/${id}-uo7.png`;
        currentImage.alt = pair.currentAlt;
        document.getElementById('compare-help').textContent = pair.help || 'Drag the divider, or use the arrow keys. Same saved scene, different camera perspectives.';
        document.getElementById('compare-u7-link').href = originalImage.src;
        document.getElementById('compare-uo7-link').href = currentImage.src;
        document.getElementById('screenshot-caption').textContent = pair.title;
        try {
            await Promise.all([originalImage.decode(), currentImage.decode()]);
        } catch {
            if (request === currentRequest) error.hidden = false;
        } finally {
            if (request === currentRequest) {
                loading.hidden = true;
                stage.setAttribute('aria-busy', 'false');
            }
        }
    }
    slider.addEventListener('input', updateSplit);
    // Pointer coordinates cover the full picture, including the extreme ends.
    // The real range input retains native keyboard and screen-reader behavior.
    function moveDivider(event) {
        const box = stage.getBoundingClientRect();
        slider.value = Math.round(Math.max(0, Math.min(100, (event.clientX - box.left) / box.width * 100)));
        updateSplit();
    }
    slider.addEventListener('pointerdown', event => {
        if (!event.isPrimary || event.button !== 0) return;
        event.preventDefault();
        slider.focus({preventScroll: true});
        slider.setPointerCapture(event.pointerId);
        moveDivider(event);
    });
    slider.addEventListener('pointermove', event => {
        if (slider.hasPointerCapture(event.pointerId)) moveDivider(event);
    });
    for (const type of ['pointerup', 'pointercancel']) slider.addEventListener(type, event => {
        if (slider.hasPointerCapture(event.pointerId)) slider.releasePointerCapture(event.pointerId);
    });
    for (const button of document.querySelectorAll('[data-compare]')) button.addEventListener('click', () => {
        showPair(button.dataset.compare);
        dialog.showModal();
        slider.focus({preventScroll: true});
    });
    for (const button of document.querySelectorAll('[data-pair]')) button.addEventListener('click', () => showPair(button.dataset.pair));
    document.getElementById('compare-retry').addEventListener('click', () => {
        showPair(activePair);
        slider.focus({preventScroll: true});
    });
    for (const button of document.querySelectorAll('[data-zoom]')) {
        button.addEventListener('click', () => {
            ++request;
            comparison.hidden = true;
            full.hidden = false;
            full.src = button.dataset.zoom;
            full.alt = button.dataset.caption;
            document.getElementById('screenshot-caption').textContent = button.dataset.caption;
            dialog.showModal();
        });
    }
    dialog.addEventListener('close', () => { ++request; });
    dialog.addEventListener('click', event => {
        if (event.target === dialog) {
            const box = dialog.getBoundingClientRect();
            if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) dialog.close();
        }
    });
})();
