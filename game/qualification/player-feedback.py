"""Regression for the local player's reported interactions, using an isolated room copy."""
import runpy
from play import ROOT
run=runpy.run_path(str(ROOT/'qualification/client-proof.py'))['run']
base=['WAIT 500','SELF','WAIT 400','INVENTORY','WAIT 400']
walk=['STEP 3','WAIT 420','STEP 3','WAIT 420','STEP 3','WAIT 420','STEP 4','WAIT 420','STEP 5','WAIT 420','WALKCHECK']
open_chest=['USE 21920','WAIT 500']
close=['CLOSE','WAIT 450']
two='CONTENTS 21936 21944'
three=two+' 9968'
actions=base+walk+['USE 13736']+open_chest+[two,'PICK 9968','GUMPDROP','WAIT 300',three]+close+open_chest+[three,'CAPTURE','PICK 9968','DROP 13736','WAIT 300',three,'PICK 9968','GROUND 987 2215','WAIT 300',two,'PICK 9968','GUMPDROP','WAIT 350',three]+close+['SAVE','EXIT']
first=run('feedback-room','Trinsic-room',actions,True,scenario='transfer')
assert any(' locked ' in line for line in first['events'])
assert any('refused3' in line for line in first['events'])
assert any(' GROUND ' in line and ' ok ' in line for line in first['events'])
again=run('feedback-room','Trinsic-room',open_chest+[three,'CAPTURE']+close+['SELF','WAIT 400','INVENTORY','WAIT 450','TURN 0','EXIT'],False,scenario='reopened')
print('Passed walk interpolation and frame changes, Avatar inventory, native lock feedback, chest icons, refusal, retrieval, close/reopen, save and process restart.')
