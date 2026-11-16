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
            image.src = original ? 'site/inn-original.png' : 'site/inn-current.png';
            image.alt = original ? 'The Honorable Hound Inn dining room in original Ultima VII.' : 'The Honorable Hound Inn dining room recreated in ClassicUO.';
            caption.textContent = original ? 'The original Ultima VII room. Different camera, familiar details.' : 'The Inn dining room, captured in our development build.';
            for (const sibling of document.querySelectorAll('[data-view]')) sibling.setAttribute('aria-pressed', String(sibling === button));
        });
    }
    const dialog = document.getElementById('screenshot-dialog');
    for (const button of document.querySelectorAll('[data-zoom]')) {
        button.addEventListener('click', () => {
            const full = document.getElementById('screenshot-image');
            full.src = button.dataset.zoom;
            full.alt = button.dataset.caption;
            document.getElementById('screenshot-caption').textContent = button.dataset.caption;
            dialog.showModal();
        });
    }
    dialog.addEventListener('click', event => {
        if (event.target === dialog) {
            const box = dialog.getBoundingClientRect();
            if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) dialog.close();
        }
    });
})();
