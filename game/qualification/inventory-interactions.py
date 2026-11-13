"""Play inventory gestures through ClassicUO mouse hit-testing and verify native ownership."""
import runpy
from play import ROOT

run = runpy.run_path(str(ROOT/'qualification/client-proof.py'))['run']
name = 'inventory-interaction-proof'
first = ['WAIT 700', 'WORN 80 Pants', 'WORN 176 Shoes', 'CAPTURE',
         'DRAGICON 176 sheet pack 68 86', 'PACKCHECK 176', 'CAPTURE',
         'DRAGICON 176 pack sheet 110 120', 'WORN 176 Shoes', 'CAPTURE',
         'DRAGICON 128 pack sheet 110 120', 'WORN 128 TwoHanded',
         'DRAGICON 128 sheet pack 92 86', 'PACKCHECK 128',
         'DRAGICON 128 pack pack 119 85', 'ICONPOSITION 128 96 68',
         'DRAGICON 104 pack sheet 110 120', 'PACKCHECK 104']
for direction in [3, 3, 3, 4, 5]:
    first += [f'STEP {direction}', 'WAIT 420']
first += ['USE 21920','WAIT 500','DRAGICON 21944 chest sheet 110 120','OWNER 21944 21920',
          'DRAGICON 112 sheet pack 62 65','PACKCHECK 112',
          'DRAGICON 21944 chest sheet 110 120','WORN 21944 OneHanded',
          'DRAGICON 21936 chest pack 80 72','PACKCHECK 21936',
          'DRAGICON 21936 pack chest 91 122','OWNER 21936 21920',
          'DRAGICON 21936 chest pack 80 72','PACKCHECK 21936','CLOSE','WAIT 450','SAVE','EXIT']
result = run(name,'Trinsic-room',first,True,scenario='drag')
assert any(' occupied ' in event for event in result['events'])
assert any(' notwearable ' in event for event in result['events'])
run(name,'Trinsic-room',['WAIT 600','WORN 21944 OneHanded','WORN 176 Shoes','PACKCHECK 21936','PACKCHECK 112',
                         'DRAGICON 21944 sheet pack 61 72','DRAGICON 112 pack sheet 110 120',
                         'WORN 112 OneHanded','EXIT'],False,scenario='restart')
print('Verified mouse pickup, equip, unequip, rejection, reposition, chest transfers and restart.')
