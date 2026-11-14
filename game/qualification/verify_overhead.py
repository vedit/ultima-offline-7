"""Check Iolo and Petre's original opening reactions on their ClassicUO mobiles."""
from pathlib import Path
import runpy

if __name__ == '__main__':
    run = runpy.run_path(str(Path(__file__).with_name('client-proof.py')))['run']
    iolo = 'WAITBARK Iolo "There, there..."'
    petre = 'WAITBARK Petre "\'Tis horrible!"'
    actions = ['BEGIN', iolo, 'RECONNECT', iolo, petre, 'EXIT']
    result = run('npc-opening-barks', 'Investigation', actions, True,
                 scenario='overhead', original_opening=True)
    observations = [line.split(' (', 1)[0] for line in result['events']
                    if line.startswith(('NPC overhead ', 'RECONNECTED -> S '))]
    assert (len(observations) == 4 and observations[0] == 'NPC overhead Iolo'
            and observations[1].startswith('RECONNECTED -> S ')
            and observations[2:] == ['NPC overhead Iolo', 'NPC overhead Petre']), observations
    from play import ROOT
    assert 'TRINSIC interaction timeout/error' not in (ROOT/'runs/npc-opening-barks/client.log').read_text()
    print('Verified both speakers and the single live Iolo reaction after reconnect.')
