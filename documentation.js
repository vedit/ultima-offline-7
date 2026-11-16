// Public documentation is intentionally read-only: no review state or storage.
(() => {
    'use strict';
    const data = DOCUMENTATION, rooms = data.mode === 'interiors';
    const $ = id => document.getElementById(id);
    const container = $(rooms ? 'homes' : 'cards');
    const groups = {homes: 'Homes', inn: 'Inn', public: 'Public buildings'};
    const frames = new Map();
    let activeGroup = 'homes', activeCategory = 'All', lastFocus;
    const node = (tag, text, cls) => {const n = document.createElement(tag); if(text !== undefined) n.textContent = text; if(cls) n.className = cls; return n;};
    const button = (text, action) => {const b = node('button', text); b.type = 'button'; b.onclick = action; return b;};
    const link = (text, url) => {const a = node('a', text); a.href = url; return a;};
    const searchable = c => [c.name, c.family, c.room, c.shape, c.description, groups[c.group], ...(c.details || []).map(d => d.name+' '+d.description)].join(' ').toLocaleLowerCase();

    function locationState() {
        const url = new URL(location.href), hash = decodeURIComponent(url.hash.slice(1));
        if (data.aliases[hash]) {
            const target = new URL(data.aliases[hash], location.href);
            if (target.pathname !== url.pathname) {location.replace(target.href); return false;}
            if (url.searchParams.has('q')) target.searchParams.set('q', url.searchParams.get('q'));
            history.replaceState(null, '', target);
            return locationState();
        }
        $('search').value = url.searchParams.get('q') || '';
        activeGroup = groups[url.searchParams.get('group')] ? url.searchParams.get('group') : 'homes';
        activeCategory = url.searchParams.get('category') || 'All';
        const room = data.cards.find(c => c.id === hash || (c.details || []).some(d => d.id === hash));
        if (rooms && room && !url.searchParams.get('q')) {
            activeGroup = room.group;
            url.searchParams.set('group', activeGroup);
            history.replaceState(null, '', url);
        }
        return true;
    }
    function updateURL(push = false, clearHash = true) {
        const url = new URL(location.href);
        if (clearHash) url.hash = '';
        if ($('search').value) url.searchParams.set('q', $('search').value); else url.searchParams.delete('q');
        if (rooms) url.searchParams.set('group', activeGroup);
        else if (activeCategory !== 'All') url.searchParams.set('category', activeCategory); else url.searchParams.delete('category');
        history[push ? 'pushState' : 'replaceState'](null, '', url);
    }
    function zoom(src, title, trigger) {
        lastFocus = trigger;
        $('zoom-title').textContent = title;
        $('zoom').classList.toggle('paper-zoom', trigger.classList.contains('paper'));
        const img = $('zoom-image'); img.alt = title; img.src = src;
        img.style.width = ''; img.style.maxWidth = '100%';
        $('zoom').showModal();
    }
    $('close-zoom').onclick = () => $('zoom').close();
    $('zoom').addEventListener('close', () => lastFocus?.focus());
    document.querySelectorAll('[data-zoom]').forEach(b => b.onclick = () => {
        const img = $('zoom-image'), scale = b.dataset.zoom;
        img.style.maxWidth = scale === 'fit' ? '100%' : 'none';
        img.style.width = scale === 'fit' ? '' : img.naturalWidth * Number(scale) + 'px';
    });
    function figure(src, caption, kind, enlargement = 1) {
        const f = node('figure');
        if (src) {
            const b = button('', () => zoom(src, caption, b));
            b.className = kind || 'stage'; b.setAttribute('aria-label', 'Enlarge '+caption);
            const img = node('img'); img.src = src; img.alt = caption; img.decoding = 'async';
            if (enlargement !== 1) img.onload = () => {img.style.width = img.naturalWidth * enlargement+'px';};
            b.append(img); f.append(b);
        } else f.append(node('div', caption.includes('paperdoll') ? 'No '+caption.split(' ·')[0].toLowerCase()+' preview' : 'Artwork unavailable', 'stage'));
        f.append(node('figcaption', caption)); return f;
    }
    function equipmentCard(c) {
        const a = node('article'); a.id = c.id;
        const head = node('header'), title = node('div'); title.append(node('h2', c.name), node('small', c.family || c.category));
        const anchor = link('U7 '+c.shape, '#'+c.id); anchor.className = 'permalink';
        head.append(title, anchor); a.append(head);
        const frameBar = node('div', undefined, 'frame'), comparison = node('div', undefined, 'comparison');
        const originalFrames = c.frames || [], count = Math.max(originalFrames.length, (c.groundFrames || []).length, 1);
        const frameLabel = node('span');
        function pictures() {
            const frame = frames.get(c.id) || 0, source = $('source-view').value === 'detail' ? c.detailFrames || originalFrames : originalFrames;
            const female = $('paperdoll').value === 'female', animate = $('animate').checked;
            const ground = (frame === 0 && animate && c.groundMotion) || c.groundFrames?.[frame % c.groundFrames.length] || c.ground;
            const worn = female ? c.wornFemaleMotion && animate ? c.wornFemaleMotion : c.wornFemale : c.wornMotion && animate ? c.wornMotion : c.worn;
            const sourceFrame = originalFrames.length === 1 ? Number(c.shape.split('/')[1]) : frame;
            comparison.replaceChildren(
                figure(source[frame % source.length], 'Ultima VII · frame '+sourceFrame, 'stage', $('source-view').value === 'original' ? 4 : 1),
                figure(ground, 'Ground artwork', 'stage', 3),
                figure(worn, (female ? 'Female' : 'Male')+' paperdoll · composite', 'stage paper'));
            frameLabel.textContent = 'Frame '+(frame+1)+' of '+count;
        }
        if (count > 1) {
            const prev = button('‹', () => {frames.set(c.id, ((frames.get(c.id)||0)-1+count)%count); pictures();});
            const next = button('›', () => {frames.set(c.id, ((frames.get(c.id)||0)+1)%count); pictures();});
            prev.setAttribute('aria-label', 'Previous frame for '+c.name); next.setAttribute('aria-label', 'Next frame for '+c.name);
            frameLabel.setAttribute('aria-live', 'polite'); frameBar.append(prev,frameLabel,next); a.append(frameBar);
        }
        a.append(comparison, node('p', c.description, 'note')); pictures(); return a;
    }
    function roomPair(c) {
        const pair = node('div', undefined, c.original ? 'pair' : 'pair single');
        if(c.original) pair.append(figure(c.original, 'Original Ultima VII', 'image-button'));
        pair.append(figure(c.current, c.representation, 'image-button')); return pair;
    }
    function roomCard(c) {
        const a = node('article'); a.id = c.id;
        const head = node('header'), titles = node('div');
        titles.append(node('span', groups[c.group], 'room-label'), node('h2', c.name), node('p', c.room, 'card-subtitle'));
        head.append(titles, link('Link to room', '?group='+c.group+'#'+c.id));
        a.append(head, roomPair(c), node('p', c.description));
        if(c.capturedAt) a.append(node('small', 'Capture: '+c.capturedAt.slice(0,10)));
        for(const d of c.details || []) {
            const detail = node('div', undefined, 'detail'); detail.id = d.id;
            detail.append(node('h3', d.name), node('p', d.description), roomPair(d)); a.append(detail);
        }
        return a;
    }
    function render() {
        const q = $('search').value.trim().toLocaleLowerCase();
        const matches = data.cards.filter(c => (!q || searchable(c).includes(q)) && (rooms ? q || c.group === activeGroup : activeCategory === 'All' || c.category === activeCategory));
        container.replaceChildren();
        $('results').textContent = matches.length ? matches.length+' '+(rooms ? 'rooms' : 'items')+(rooms && q ? ' across all interior groups' : '') : 'No matching '+(rooms?'rooms':'items')+'. Try another search.';
        if (rooms) {
            $('groups').querySelectorAll('a').forEach(a => {if(a.dataset.group===activeGroup)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
            $('room-links').replaceChildren();
            for(const [group,label] of Object.entries(groups)) {
                const list = matches.filter(c=>c.group===group); if(!list.length)continue;
                if(q) $('room-links').append(node('span',label,'group-label'));
                for(const c of list) {
                    const target = new URL(location.href); target.searchParams.set('group',group); target.hash=c.id;
                    $('room-links').append(link(c.name+' · '+c.room,target.pathname+target.search+target.hash));
                }
                container.append(node('h2',label,'section-heading'), ...list.map(roomCard));
            }
        } else {
            $('categories').querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed',String(b.textContent===activeCategory)));
            for(const section of data.mode === 'armory' ? ['Weapons','Ammunition'] : ['Armor','Shields','Boots','Accessories']) {
                const list = matches.filter(c=>c.category===section); if(!list.length)continue;
                const heading = node('h2',section,'section-heading'); heading.id = section.toLowerCase();
                container.append(heading);
                if (section === 'Weapons') {
                    for (const family of new Set(list.map(c=>c.family))) {
                        container.append(node('h3', family, 'family-heading'), ...list.filter(c=>c.family===family).map(equipmentCard));
                    }
                } else container.append(...list.map(equipmentCard));
            }
        }
        if(!matches.length)container.append(node('p','No matches. Clear the search or choose another category.','empty'));
    }
    function jump() {if(location.hash) requestAnimationFrame(()=>document.getElementById(decodeURIComponent(location.hash.slice(1)))?.scrollIntoView({block:'start'}));}
    if(rooms) {
        for(const [group,label] of Object.entries(groups)) {
            const a=link(label,'?group='+group);a.dataset.group=group;
            a.onclick=e=>{e.preventDefault();activeGroup=group;$('search').value='';updateURL(true);render();};$('groups').append(a);
        }
    } else {
        for(const category of ['All',...new Set(data.cards.map(c=>c.category))]) {
            $('categories').append(button(category,()=>{activeCategory=category;updateURL(true);render();}));
        }
        for(const id of ['source-view','paperdoll','animate'])$(id).onchange=render;
    }
    $('search').oninput=()=>{updateURL();render();};
    addEventListener('popstate',()=>{if(locationState()){render();jump();}});
    addEventListener('hashchange',()=>{if(locationState()){render();jump();}});
    if(locationState()){render();jump();}
})();
