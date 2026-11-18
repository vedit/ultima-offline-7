"""Copy the reviewed social artwork; keep promotional composites separate from captures."""
import hashlib
import json
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / 'site'


def install_social(output, artwork):
    output, artwork = Path(output), Path(artwork)
    manifest = json.loads((SOURCE / 'social-assets.json').read_text(encoding='utf-8'))
    prepared = {}
    for asset in manifest['assets']:
        path = artwork / asset['name']
        if not path.is_file():
            raise ValueError(f'Missing social artwork {asset["name"]}; supply --social-assets from the current Pages site/social directory')
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != asset['sha256']:
            raise ValueError(f'Social artwork differs from reviewed manifest: {asset["name"]}')
        prepared['site/social/' + asset['name']] = content
    prepared['share.html'] = (SOURCE / 'share.html').read_bytes()
    prepared['site/social/sources.json'] = (json.dumps(manifest, indent=2)+'\n').encode()
    for name, content in prepared.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return set(prepared)
