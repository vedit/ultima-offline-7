"""Verify the stock windows and carried item across a process restart."""
from play import ROOT
import runpy
run=runpy.run_path(str(ROOT/'qualification/client-proof.py'))['run']
first=['WAIT 700','PANELS','REOPENPANELS','WAIT 400','PANELS','CAPTURE']
for d in [3,3,3,4,5]: first+=['STEP '+str(d),'WAIT 420']
first+=['PICK 9968','PACKDROP','WAIT 450','PACKCHECK 9968','SAVE','EXIT']
run('player-panels-proof','Trinsic-room',first,True,scenario='panels')
again=run('player-panels-proof','Trinsic-room',['WAIT 700','PANELS','PACKCHECK 9968','CAPTURE','USE 21920','WAIT 500','PICK 9968','GUMPDROP','WAIT 450','CONTENTS 21936 21944 9968','EXIT'],False,scenario='restart')
assert any('MOVE 9968 21920' in event and ' ok ' in event for event in again['events'])
print('Verified paperdoll, equipped items, minimap and backpack together, reopening, native transfer and persisted backpack ownership.')
