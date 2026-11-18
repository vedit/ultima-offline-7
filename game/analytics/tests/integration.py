"""Qualify the installer against the current published client, without running UI."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile

source=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('install_analytics',source/'install.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
pages=Path(sys.argv[1]).resolve()
baseline=sys.argv[2] if len(sys.argv)>2 else 'origin/gh-pages'
def tracked(name):
    return subprocess.check_output(['git','show',baseline+':play/'+name],cwd=pages).decode('utf-8')
js,html=tracked('client.js'),tracked('index.html')
a,b=module.transform(js,html)
assert module.transform(a,b)==(a,b), 'Installer must be idempotent'
assert a.count("telemetry.event('begin')")==2
assert 'uo7-analytics' in b and b.count('id="usage-reporting"')==1
try: module.transform(js.replace('function fail(error){','function changed(error){'),html)
except ValueError: pass
else: raise AssertionError('Changed bridge must fail closed')
target=Path(tempfile.mkdtemp(prefix='uo7-analytics-test-')).resolve()
assert target.is_relative_to(Path(tempfile.gettempdir()).resolve())
try:
    (target/'client.js').write_text(js,encoding='utf-8');(target/'index.html').write_text(html,encoding='utf-8')
    module.install(target)
    assert all((target/'analytics'/p).is_file() for p in ('core.js','browser.js','schema.js','session-v2.js','privacy.html'))
finally:
    for name in ('core.js','browser.js','schema.js','session-v2.js','privacy.html'):
        (target/'analytics'/name).unlink(missing_ok=True)
    (target/'analytics').rmdir()
    (target/'client.js').unlink();(target/'index.html').unlink();target.rmdir()
print('Integration anchors, idempotence, drift refusal and module copy passed')
