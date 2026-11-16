"""Package the project homepage using existing captures and reviewed atlas pixels."""
import base64
import hashlib
import json
from pathlib import Path

from review_snapshot import js_data


def install_homepage(output, screenshots):
    output, screenshots = Path(output), Path(screenshots)
    source = Path(__file__).resolve().parents[1] / 'site'
    files, provenance = set(), {}

    def write(name, content, origin):
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        files.add(name)
        provenance[name] = {'source': origin, 'sha256': hashlib.sha256(content).hexdigest()}

    # Require the two selected, actual client captures; never replace them with
    # generated promotional artwork or silently fall back to an older screenshot.
    captures = {name: (screenshots / name).read_bytes() for name in ('trinsic.png', 'dream.png')}
    if any(not content.startswith(b'\x89PNG\r\n\x1a\n') for content in captures.values()):
        raise ValueError('Homepage captures must be PNG screenshots')
    inn_html = (output / 'inn.html').read_text(encoding='utf8')
    inn = next(c for c in js_data(inn_html, 'HOMES')[0] if c['id'] == 'inn-dining')
    equipment_html = (output / 'armory.html').read_text(encoding='utf8')
    equipment = {c['shape']:c for c in js_data(equipment_html, 'data')[0]['cards']}

    def png(url):
        if not url.startswith('data:image/png;base64,'):
            raise ValueError('Expected original PNG review pixels')
        return base64.b64decode(url.split(',', 1)[1], validate=True)

    for name, content in captures.items():
        write('site/' + name, content, 'supplied-client-capture/' + name)
    for field in ('original', 'current'):
        write(f'site/inn-{field}.png', png(inn[field]), f'inn.html / inn-dining / {field}')
    for shape, name in ((604, 'glass-sword'), (637, 'serpentine-sword'), (663, 'magic-shield')):
        write(f'site/{name}.png', png(equipment[shape]['ground']), f'armory.html / {shape} / ground')
    for name in ('home.css', 'home.js'):
        write('site/' + name, (source / name).read_bytes(), 'game/site/' + name)
    write('index.html', (source / 'index.html').read_bytes(), 'game/site/index.html')
    receipt = {'description':'Actual development screenshots and unchanged review images; no gameplay data', 'assets':provenance}
    write('site/sources.json', (json.dumps(receipt, indent=2)+'\n').encode(), 'homepage export receipt')
    return files
