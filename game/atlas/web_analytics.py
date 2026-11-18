"""Install the site's manual Cloudflare beacon without touching the game bundle."""
from pathlib import Path
import argparse
import re


def install_web_analytics(output, pages=None):
    output = Path(output).resolve()
    snippet = (Path(__file__).resolve().parents[1] / 'site' / 'web-analytics.html').read_text(encoding='utf8').strip()
    # Standalone publication updates are limited to top-level website pages.
    # Browser game analytics belongs to game/analytics and its release contract.
    targets = sorted(output.glob('*.html')) if pages is None else [output / p for p in sorted(pages)]
    changed = []
    for path in targets:
        relative = path.resolve().relative_to(output)
        if relative.parts[0] == 'play':
            raise ValueError('Website analytics must not modify the browser game bundle')
        html = path.read_text(encoding='utf8')
        if 'static.cloudflareinsights.com/beacon.min.js' in html:
            if snippet not in html:
                raise ValueError(f'Unexpected existing Cloudflare beacon: {relative}')
            continue
        # Existing atlas aliases immediately redirect; count the destination only.
        if 'location.replace(' in html or re.search(r'http-equiv=["\']refresh["\']', html, re.I):
            continue
        updated, count = re.subn(r'</body\s*>', lambda m: snippet + '\n' + m[0], html, count=1, flags=re.I)
        if not count:
            # Some atlas documents use HTML's optional body tags.
            updated, count = re.subn(r'</html\s*>', lambda m: snippet + '\n' + m[0], html, count=1, flags=re.I)
        if count != 1:
            raise ValueError(f'Missing document end in website page: {relative}')
        path.write_text(updated, encoding='utf8', newline='\n')
        changed.append(relative.as_posix())
    return changed


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    print('\n'.join(install_web_analytics(parser.parse_args().output)))
