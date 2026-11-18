"""Package the project homepage using existing captures and reviewed atlas pixels."""
import base64
import hashlib
import json
from pathlib import Path

from review_snapshot import js_data


def install_homepage(output, screenshots, social_assets=None):
    output, screenshots = Path(output), Path(screenshots)
    source = Path(__file__).resolve().parents[1] / 'site'
    from social_preview import install_social
    files = install_social(output, social_assets or screenshots / 'social')
    provenance = {}

    def write(name, content, origin):
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        files.add(name)
        provenance[name] = {'source': origin, 'sha256': hashlib.sha256(content).hexdigest()}

    # Require both sides of each comparison, never substitute an older screenshot.
    pair_ids = ('barn-overview', 'fellowship-interior', 'guardian-dream')
    capture_names = tuple(f'{pair}-{game}.png' for pair in pair_ids for game in ('u7', 'uo7'))
    captures = {name: (screenshots / name).read_bytes() for name in capture_names}
    if any(not content.startswith(b'\x89PNG\r\n\x1a\n') for content in captures.values()):
        raise ValueError('Homepage captures must be PNG screenshots')
    paired = json.loads((screenshots / 'scene-captures.json').read_text(encoding='utf8'))
    if {pair['id'] for pair in paired['pairs']} != set(pair_ids) or len(paired['pairs']) != len(pair_ids):
        raise ValueError('Require the barn, Fellowship and Guardian comparison pairs')
    for pair in paired['pairs']:
        for game in ('u7', 'uo7'):
            name = f"{pair['id']}-{game}.png"
            if hashlib.sha256(captures[name]).hexdigest() != pair['files'][name]['sha256']:
                raise ValueError(f'Capture differs from its paired-scene receipt: {name}')
    equipment_html = (output / 'armory.html').read_text(encoding='utf8')
    equipment = {c['shape']:c for c in js_data(equipment_html, 'data')[0]['cards']}

    def png(url):
        if not url.startswith('data:image/png;base64,'):
            raise ValueError('Expected original PNG review pixels')
        return base64.b64decode(url.split(',', 1)[1], validate=True)

    for name, content in captures.items():
        write('site/' + name, content, 'supplied-client-capture/' + name)
    write('site/scene-captures.json', (json.dumps(paired, indent=2)+'\n').encode(), 'paired renderer capture receipt')
    for shape, name in ((604, 'glass-sword'), (637, 'serpentine-sword'), (663, 'magic-shield')):
        write(f'site/{name}.png', png(equipment[shape]['ground']), f'armory.html / {shape} / ground')
    for name in ('home.css', 'home.js'):
        write('site/' + name, (source / name).read_text(encoding='utf8').encode('utf8'), 'game/site/' + name)
    write('index.html', (source / 'index.html').read_text(encoding='utf8').encode('utf8'), 'game/site/index.html')
    receipt = {'description':'Actual development screenshots and unchanged review images; promotional composites are documented separately in site/social/sources.json; no gameplay data', 'assets':provenance}
    write('site/sources.json', (json.dumps(receipt, indent=2)+'\n').encode(), 'homepage export receipt')
    return files
