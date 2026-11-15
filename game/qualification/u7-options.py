"""Qualify U7 options routing, saved preferences, save/load and compact status."""
from pathlib import Path
import runpy
run=runpy.run_path(str(Path(__file__).with_name('client-proof.py')))['run']
result=run('u7-options','Investigation',[
    'WAIT 900','U7SHEET','STATUS','U7STATUS','U7OPTIONS','CAPTURE',
    'U7PREFERENCES 1 1 0','U7TOGGLE 0','U7TOGGLE 1','U7TOGGLE 2','U7PREFERENCES 0 0 1',
    'U7OPTION 1','WAIT 250','U7OPTION 2','U7LOADANSWER 0','WAIT 150',
    'U7OPTION 2','U7LOADANSWER 1','WAIT 350','U7PREFERENCES 0 0 1',
    'U7OPTION 3','WAIT 200','U7ADVANCED','U7OPTIONS','U7OPTION 4',
    'PARTYOPEN','WAIT 200','PARTYSELECT 184 sheet','PARTYSELECT 184 pack','PARTYPANELS 184',
    'STEP 0','WAIT 350','STEP 2','WAIT 350','STEP 4','WAIT 350','STEP 6','WAIT 350','WALKCHECK','EXIT',
],True,scenario='options')
for operation in ('SAVE','LOAD'):
    events=[e for e in result['events'] if f' {operation} -1 0 -> ' in e]
    assert len(events)==1 and ' ok ' in events[0], (operation,events)
run('u7-options','Investigation',[
    'WAIT 900','U7PREFERENCES 0 0 1','U7OPTIONS','U7TOGGLE 0','U7TOGGLE 1','U7TOGGLE 2',
    'U7PREFERENCES 1 1 0','U7OPTION 4','STATUS','U7STATUS','CAPTURE','EXIT',
],False,scenario='restart')
print('U7 options, save/load confirmation, persisted preferences, advanced routing, status and movement passed.')
