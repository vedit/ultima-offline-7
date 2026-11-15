"""Export the linked atlas review pages for GitHub Pages, without runtime data."""
import argparse
from collections import deque
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
from urllib.parse import unquote, urlsplit


ALLOWED = {'.html', '.png', '.js', '.css', '.csv', '.json'}
REPO = 'https://github.com/vedit/ultima-offline-7'
PATH_PATTERN = re.compile(r'(?:file:///|(?<![A-Za-z])[A-Za-z]:[\\/])')


class Links(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.urls = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.urls.extend(value for key, value in attrs if key in ('src', 'href') and value)


def local_link(url, page, root):
    if url.startswith('file:///'):
        # Old review pages linked back to their local atlas. Only rewrite a
        # link that is actually inside this selected atlas.
        original = Path(unquote(url[8:])).resolve()
        if not original.is_relative_to(root):
            raise ValueError(f'File link leaves the selected atlas: {page}')
        return original.relative_to(root).as_posix()
    parts = urlsplit(url)
    if parts.scheme or parts.netloc or not parts.path:
        return None
    path = (root / page).parent / unquote(parts.path)
    if not path.resolve().is_relative_to(root):
        raise ValueError(f'Link leaves the atlas: {page}: {url}')
    return path.relative_to(root).as_posix()


def logical_path(value):
    normalized = value.replace('\\', '/')
    for marker, prefix in (('/Assets/', 'local-assets/'), ('/Tools/', 'dependencies/'), ('/game/', 'project/')):
        if marker.lower() in normalized.lower():
            i = normalized.lower().index(marker.lower())
            return prefix + normalized[i + len(marker):]
    return 'local-input/' + hashlib.sha256(value.encode()).hexdigest()[:12] + '/' + normalized.rsplit('/', 1)[-1]


def scrub(value):
    if isinstance(value, dict):
        result = {}
        for key, child in value.items():
            clean = logical_path(key) if PATH_PATTERN.search(key) else key
            if clean in result:
                raise ValueError('Input fingerprint labels collide')
            result[clean] = scrub(child)
        return result
    if isinstance(value, list):
        return [scrub(child) for child in value]
    if isinstance(value, str) and PATH_PATTERN.search(value):
        return logical_path(value)
    return value


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export(atlas, output):
    atlas, output = atlas.resolve(), output.resolve()
    if atlas == output or atlas.is_relative_to(output) or output.is_relative_to(atlas):
        raise ValueError('Export must be separate from the source atlas')
    if output.exists() and any(p.name != '.git' for p in output.iterdir()):
        raise ValueError('Use an empty export directory (a new Pages worktree may contain .git)')
    text = (atlas / 'catalog.js').read_text(encoding='utf-8-sig')
    match = re.fullmatch(r'\s*const CATALOG\s*=\s*(\[.*\]);\s*', text, re.S)
    if not match:
        raise ValueError('Unknown atlas catalog format')
    catalog = json.loads(match[1])
    queue = deque(['index.html', 'catalog.js'])
    for row in catalog:
        for field in ('source_image', 'target_image', 'detail_image'):
            if value := row.get(field):
                if not re.fullmatch(r'[a-f0-9]+', value):
                    raise ValueError(f'Invalid catalog image key: {field}')
                queue.append(f'images/{value}.png')
    selected, pages = set(), {}
    names = {p.relative_to(atlas).as_posix() for p in atlas.rglob('*') if p.is_file()}
    while queue:
        name = queue.popleft()
        if name in selected:
            continue
        if name not in names or Path(name).suffix not in ALLOWED:
            raise ValueError(f'Missing or unsupported website dependency: {name}')
        selected.add(name)
        if name.endswith('.html'):
            html = (atlas / name).read_text(encoding='utf-8-sig')
            for url in Links(html).urls:
                target = local_link(url, name, atlas)
                if target:
                    queue.append(target)
                    if url.startswith('file:///'):
                        html = html.replace(url, target)
            if PATH_PATTERN.search(html):
                raise ValueError(f'Unresolved local path in {name}')
            pages[name] = html

    output.mkdir(parents=True, exist_ok=True)
    nav = [('index.html', 'Atlas'), ('homes.html', 'Homes'), ('inn.html', 'Inn'),
           ('public-interiors.html', 'Public interiors'), ('armory.html', 'Armory'), ('shields.html', 'Shields')]
    links = ' '.join(f'<a href="{url}">{label}</a>' for url, label in nav if url in selected)
    style = '<style>.atlas-site-nav{max-width:1510px;margin:0 auto;padding:16px clamp(16px,4vw,60px);display:flex;flex-wrap:wrap;gap:10px 20px;font:14px/1.5 system-ui,sans-serif;border-bottom:1px solid #45575a}.atlas-site-nav a{color:#aadad5}.atlas-site-nav strong{color:#edf1e8;margin-right:auto}.atlas-site-note{font:12px/1.5 system-ui,sans-serif;color:#b5c5c2;margin:24px 0}.atlas-site-note a{color:#aadad5}</style>'
    header = style + f'<nav class="atlas-site-nav" aria-label="Atlas pages"><strong>Ultima Offline 7</strong>{links} <a href="{REPO}">GitHub</a></nav>'
    note = '<p class="atlas-site-note">Public review snapshot. Candidate and approval labels describe artwork review, not guaranteed in-game coverage. Ultima VII and Ultima Online artwork belongs to its respective rights holders. <a href="publication.json">Snapshot details</a></p>'
    for name in sorted(selected):
        dest = output / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if name in pages:
            html = pages[name]
            html, count = re.subn(r'(<main\b[^>]*>)', lambda m: header + m[0], html, count=1)
            if not count:
                raise ValueError(f'No gallery main element in {name}')
            html = html.replace('</main>', note + '</main>', 1)
            dest.write_text(html, encoding='utf8', newline='\n')
        elif name.endswith('.json'):
            payload = scrub(json.loads((atlas / name).read_text(encoding='utf-8-sig')))
            # Exported HTML changes navigation and paths; don't advertise stale hashes.
            payload.pop('output_sha256', None)
            dest.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf8')
        else:
            shutil.copyfile(atlas / name, dest)
    (output / '.nojekyll').write_text('')
    metadata = dict(published_at=datetime.now(timezone.utc).isoformat(),
                    source_updated_at=datetime.fromtimestamp((atlas / 'index.html').stat().st_mtime, timezone.utc).isoformat(),
                    rows=len(catalog), pages=sorted(pages), files=len(selected),
                    bytes=sum((output / p).stat().st_size for p in selected),
                    source_catalog_sha256=sha(atlas / 'catalog.js'),
                    scope='Linked review galleries and catalog thumbnails; runtime files and unlinked old revisions excluded',
                    output_sha256={p:sha(output / p) for p in sorted(selected) if not p.startswith('images/')})
    (output / 'publication.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf8')
    print(json.dumps({k:v for k,v in metadata.items() if k != 'output_sha256'}, indent=2))
    return metadata


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--atlas', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    export(args.atlas, args.out)
