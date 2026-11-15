"""Exercise the U7-only paperdoll and native companion roster through mouse input."""
from pathlib import Path
import runpy
run=runpy.run_path(str(Path(__file__).with_name('client-proof.py')))['run']
run('paperdoll-controls','Investigation',[
    'WAIT 900','U7SHEET','CAPTURE','PARTYOPEN','WAIT 250','CAPTURE',
    'PARTYSELECT 184 sheet','WAIT 200','PARTYSELECT 184 pack','WAIT 250','PARTYPANELS 184','CAPTURE',
    'RECONNECT','WAIT 350','U7SHEET','SAVE','LOAD','WAIT 400','U7SHEET',
    'SELF','WAIT 200','PARTYOPEN','WAIT 250','PARTYSELECT 184 sheet','WAIT 200',
    'PARTYSELECT 184 pack','WAIT 200','PARTYPANELS 184',
    'STEP 0','WAIT 350','STEP 2','WAIT 350','STEP 4','WAIT 350','STEP 6','WAIT 350','WALKCHECK','EXIT',
],True,scenario='u7-controls')
print('U7 paperdoll buttons, Party button, actual companion roster, mouse-opened equipment/inventory, reconnect/load and movement passed.')
