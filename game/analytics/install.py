"""Apply the optional telemetry module to a prepared browser client, idempotently.

Run after prepare_pages.py / prepare_auto_host.py. It edits only client.js,
index.html and analytics/, and fails before writing if the integration changed.
"""
import argparse
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
ENDPOINT = 'https://telemetry.ultimaoffline7.com/collect'
BOOT = '''// UO7 analytics integration v1 (optional; failures cannot stop the game).
const telemetry = (()=>{
    let sink, pending=[];
    import('./analytics/browser.js?v=1').then(({connect})=>{
        sink=connect(buildVersion);
        for(const args of pending)sink.event(...args);
        pending=[];
    }).catch(()=>{pending=[];sink={event(){}}});
    return {event(type,value){try{
        const args=[type,value,performance.now()];
        if(sink)sink.event(...args);else if(pending.length<64)pending.push(args);
    }catch{}}};
})();
'''

def transform(js, html):
    if '// UO7 analytics integration v1' in js:
        if 'id="usage-reporting"' not in html or 'name="uo7-analytics"' not in html:
            raise ValueError('Partial analytics integration: review both client.js and index.html')
        return js, html
    def replace(old, new):
        nonlocal js
        if js.count(old) != 1:
            raise ValueError(f'Client integration anchor changed: {old[:70]}')
        js = js.replace(old, new)
    anchor="const buildVersion=new URL(import.meta.url).searchParams.get('v')||'dev';"
    replace(anchor, anchor+'\n'+BOOT)
    replace('function loadingStep(message,percent,detail){',
        "function loadingStep(message,percent,detail){telemetry.event('stage',percent<5?'startup':percent<50?'download':percent<55?'save':percent<92?'client':percent<97?'artwork':'render');")
    replace('globalThis.__uo_signal=name=>{', "globalThis.__uo_signal=name=>{\n    if(name==='draw-heartbeat')telemetry.event('draw');\n    if(name==='paused'||name==='resumed')telemetry.event('paused',name==='paused');")
    replace('function fail(error){', "function fail(error){telemetry.event('fail');")
    replace('function publishFrame(frame){', "function publishFrame(frame){telemetry.event('frame',frame);")
    replace('async function launch(){', "async function launch(){\n    telemetry.event('begin');")
    replace('mailbox=new Int32Array(new SharedArrayBuffer(65536));',
        "telemetry.event('stage','native');\n        mailbox=new Int32Array(new SharedArrayBuffer(65536));")
    anchor="setTimeout(()=>{status.textContent='Browser setup did not finish."
    replace(anchor,"setTimeout(()=>{telemetry.event('begin');telemetry.event('fail');status.textContent='Browser setup did not finish.")
    if html.count('<meta name="uo-api-base"')!=1 or html.count('<button id="play"')!=1:
        raise ValueError('Launcher integration anchors changed')
    html=html.replace('<meta name="uo-api-base"',f'<meta name="uo7-analytics" content="{ENDPOINT}">\n<meta name="uo-api-base"')
    html=html.replace('<button id="play"', '''<div class="field" id="usage-settings">
<label style="font-size:14px;font-weight:400"><input type="checkbox" id="usage-reporting" checked> Share anonymous playtime and progress</label>
<p class="hint">Helps improve the playtest. Reports loading results, time played and investigation milestones using a new ID each launch. No character names, game files or saves are sent. <a href="./analytics/privacy.html" target="_blank" rel="noopener" style="color:#d9bd7c">Details</a>. Changes apply to your next launch.</p>
</div>
<button id="play"''')
    return js, html

def install(target):
    target=Path(target).resolve()
    js,html=transform((target/'client.js').read_text(encoding='utf-8'),(target/'index.html').read_text(encoding='utf-8'))
    (target/'analytics').mkdir(exist_ok=True)
    for name in ('core.js','browser.js','privacy.html'):
        shutil.copyfile(HERE/name,target/'analytics'/name)
    (target/'client.js').write_text(js,encoding='utf-8')
    (target/'index.html').write_text(html,encoding='utf-8')
    print(f'Installed optional playtime analytics: {target}')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('prepared_client',type=Path)
    install(parser.parse_args().prepared_client)
