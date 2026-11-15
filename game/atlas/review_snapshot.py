"""Reconcile the November 2026 Atlas reviews without regenerating game artwork.

The installed armory HTML predates the eight review batches. Later small reviews
are overlays, not complete replacement catalogs. Keep that precedence explicit.
"""
import base64
import hashlib
import json
from pathlib import Path
import re


def js_data(html, variable):
    match = re.search(r'const\s+' + re.escape(variable) + r'\s*=\s*', html)
    if not match:
        raise ValueError(f'Missing review data: {variable}')
    value, length = json.JSONDecoder().raw_decode(html[match.end():])
    return value, (match.end(), match.end() + length)


def reconcile_cards(base, lore, guard, shields):
    """Keep ordinary boots, but replace superseded daggers/ring states."""
    cards = [dict(c) for c in base if c['shape'] not in (561, 564, 759)]
    for card in lore:
        if str(card['shape']).endswith('-approved'):
            continue  # Older comparison references, not the accepted revisions.
        cards.append(dict(card, approved=True, reference=True, initialStatus='Looks good'))
    by_shape = {c['shape']: c for c in cards}
    for shape, replacement in shields.items():
        by_shape[shape].update(replacement, approved=True, reference=True, initialStatus='Looks good')
    by_shape[637].update(guard, approved=True, reference=True, initialStatus='Looks good')
    by_shape[702].update(approved=True, reference=True, initialStatus='Looks good')
    for c in cards:
        c['batch'] = False
    identities = [str(c['shape']) for c in cards]
    if len(set(identities)) != len(identities):
        raise ValueError('Duplicate equipment identities in review snapshot')
    return cards


def build_reviews(reviews, guard_ground):
    reviews, guard_ground = Path(reviews).resolve(), Path(guard_ground).resolve()
    receipts = {}

    def read(relative, root=reviews):
        path = root / relative
        content = path.read_bytes()
        label = ('reviews/' if root == reviews else 'approved-guard/') + relative
        receipts[label] = hashlib.sha256(content).hexdigest()
        return content

    def page(relative):
        return read(relative).decode('utf-8-sig').replace('\r\n', '\n')

    def image(relative, root=reviews):
        mime = 'webp' if relative.endswith('.webp') else 'png'
        return f'data:image/{mime};base64,' + base64.b64encode(read(relative, root)).decode('ascii')

    base, _ = js_data(page('armory-batch8-revision2/weapons-armor-revised.html'), 'data')
    template = page('armory-lore-preview1/lore-equipment-review.html')
    lore, bounds = js_data(template, 'data')
    guard_cards, _ = js_data(page('swept-guard-review/atlas/armory.html'), 'cards')
    guard = dict(next(c for c in guard_cards if c['shape'] == 637))
    guard['groundFrames'] = [image(f'637-{f}.png', guard_ground) for f in range(5)]
    guard.update(ground=guard['groundFrames'][0], reviewNote='Approved swept guard and continuous ground hilt contour; five native facings.')

    shield_html = page('shield-approved-review/index.html')
    shields = {}
    for article in re.findall(r'<article>(.*?)</article>', shield_html, re.S):
        shape = int(re.search(r'<h2>[^<]*\[(\d+)\]', article)[1])
        images = re.findall(r'<img\b[^>]*\bsrc="([^"]+)"', article)
        if len(images) != 5 or images[1] != images[2]:
            raise ValueError('Unknown approved shield comparison layout')
        shields[shape] = dict(ground=images[1], worn=images[3], reviewNote='Approved and installed: compact ground sprite and converted paperdoll. ' + ('Only the valorite rim shimmers in game.' if shape == 663 else 'Silver face, charcoal serpent and dark steel rim.'))
    if set(shields) != {545, 663}:
        raise ValueError('Both approved shield designs are required')
    cards = reconcile_cards(base['cards'], lore['cards'], guard, shields)
    for c in cards:
        if c['shape'] == '564/0':
            c['name'] = 'poison dagger — serpent tooth'
            c['reviewNote'] = 'Accepted lore revision: organic fang with an ivory ridge and emerald enamel on the native UO dagger hilt.'
        if c['shape'] == 620:
            c.update(approved=True, reference=True, initialStatus='Looks good')

    # The accepted shimmer pass also contains the final static magic-item pixels.
    # The two redesigned shields postdate it: never restore the older kite shield.
    shimmer, _ = js_data(page('armory-shimmer-preview2/shimmer-review.html'), 'cards')
    for c in cards:
        key = str(c['shape']).replace('/', '-')
        if '-' not in key:
            key += '-0'
        if key == '663-0' or key not in {s['key'] for s in shimmer}:
            continue
        stem = 'armory-shimmer-preview2/' + key
        c.update(ground=image(stem+'-ground-off.png'), worn=image(stem+'-worn-off.png'),
                 groundMotion=image(stem+'-ground.webp'), wornMotion=image(stem+'-worn.webp'))
    digest = hashlib.sha256(json.dumps(receipts, sort_keys=True).encode()).hexdigest()
    data = dict(cards=cards, batch=[], revision=False, sourceHash=digest,
                reviewId='public-consolidated-'+digest[:16], heading='Weapons and armour',
                introduction='The Atlas review collection: eight equipment batches, accepted magical-item revisions, approved shield designs and the final serpentine guard. Weapons open first; choose a family to explore armour, shields and ammunition.',
                explanation='U7 originals and ground sprites are enlarged. Paperdolls are asset composites, not live captures. Animated previews use the accepted shimmer pass; the later magic shield has its own installed comparison page. Approval labels record the reviewed version, while local feedback belongs only to this browser. See the interior pages for live room captures.',
                batchLabel='All reviewed batches')
    html = template[:bounds[0]] + json.dumps(data, ensure_ascii=False) + template[bounds[1]:]
    html = html.replace('</style>', 'input[type=checkbox]{width:auto;justify-self:start}</style>', 1)
    html = html.replace('../shield-approved-review/index.html', 'shields.html')
    html = html.replace('<option value="batch">First batch · 12 items</option>', '')
    html = html.replace("document.querySelector('#scope option[value=batch]').textContent=data.batchLabel;", '')
    html = html.replace('<button class="primary" id="export">', '<label><input type="checkbox" id="animate" checked> Animate magic</label><button class="primary" id="export">')
    html = html.replace("figure(c.ground||c.image,", "figure(($('animate').checked&&c.groundMotion)||c.ground||c.image,")
    html = html.replace("figure(c.worn,'Current paperdoll'", "figure(($('animate').checked&&c.wornMotion)||c.worn,'Current paperdoll'")
    html = html.replace("$('scope').onchange=$('family').onchange=$('search').oninput=render;render();",
                        "$('scope').value='all';$('family').value='Weapon';$('animate').onchange=$('scope').onchange=$('family').onchange=$('search').oninput=render;render();")
    if "$('family').value='Weapon'" not in html:
        raise ValueError('Unknown equipment review controls')
    pages = {'armory.html': html,
             'public-interiors.html': page('public-interiors-review/index.html'),
             'shields.html': shield_html.replace('../inn-review/index.html', 'inn.html'),
             'inn.html': page('inn-review/index.html').replace('../shield-approved-review/index.html', 'shields.html')}
    return pages, {'recipe': 'atlas-reviews-2026-11-16', 'equipment_entries': len(cards),
                   'source_sha256': receipts,
                   'precedence': ['Eight-batch review', 'Accepted lore variants', 'Accepted shimmer', 'Approved shield replacements and final guard contour']}
