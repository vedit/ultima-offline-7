"""Generate the isolated playtest by relocating three existing records in the native engine."""
from pathlib import Path
import json,shutil,hashlib
from play import session, Pipe
from reference import ROOT,EVIDENCE,members,sha
donor=EVIDENCE/'dos-reference/session-jrKbjq/mayoral-hall-GAME05.U7'
assert sha(donor)=='036cdce2bed0a9364f65debe5647a929246e7f77986bc6f24872a32624d5f31f' and members(donor)['FLAGINIT'][72]==0
shutil.copyfile(donor,ROOT/'fixtures/Mayoral-hall-source.U7')
with session('fixture-room','Mayoral-hall-source',True,{'TRINSIC_PREPARE':'room'}) as (folder,env,host):
    p=Pipe(env['TRINSIC_PIPE'],host)
    before=p.rows
    assert p.send('PREPARE')=='ok'
    assert p.send('SAVE')=='ok'
    p.close()
    save=folder/'GAME00.U7'
    assert members(save)['FLAGINIT'][72]==0
    shutil.copyfile(save,ROOT/'fixtures/Trinsic-room.U7')
    (ROOT/'evidence/room-setup.json').write_text(json.dumps(dict(donor=str(donor),input_sha256=sha(donor),save_sha256=sha(save),original=[r for r in before if r[1] in (994,800,522) and tuple(r[3:5]) in ((1079,2185),(962,2221),(1050,2278))],setup='native Item_forceMove into the east doorway area; no flag edits'),indent=2))

