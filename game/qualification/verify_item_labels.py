"""Click scenery, the stable sign, backpack gold and worn armour in the playable client."""
from pathlib import Path
import runpy

if __name__ == '__main__':
    run = runpy.run_path(str(Path(__file__).with_name('client-proof.py')))['run']
    clicks = [('STATICLOOK', 'LABELCHECK'), ('PIXELLOOK 11608', 'LABELCHECK sign'),
              ('MONEY look', 'LABELCHECK'), ('SHEETLOOK Torso', 'LABELCHECK leather armour')]
    actions = ['WAIT 700']
    for click, check in clicks:
        actions.extend([click, 'MOVECURSOR', 'WAIT 650', check])
    actions.extend(['WAIT 4250', 'LABELEXPIRED', 'EXIT'])
    run('verify-item-click-labels', 'Investigation', actions, True, scenario='item-label')
    print('Verified single-click labels at the original click position on all four targets and their expiry.')
