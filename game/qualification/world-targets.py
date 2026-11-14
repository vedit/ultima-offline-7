"""Verify coordinate, object and cancellation targeting without changing retail scripts."""
import runpy
import time
from pathlib import Path
from play import session

audit = runpy.run_path(str(Path(__file__).with_name('item-use-audit.py')))
BoundedPipe, settle, movement = (audit[k] for k in ('BoundedPipe', 'settle', 'movement'))


def wait_target(p):
    end = time.monotonic()+6
    while time.monotonic()<end:
        p.sync()
        if int(p.head[9])==4: return int(p.head[10])
        time.sleep(.025)
    raise AssertionError(('No target prompt', p.head))


def native():
    with session('world-target-native', 'Investigation', True) as (folder, env, host):
        p = BoundedPipe(env['TRINSIC_PIPE'], host)
        assert p.send('USE', 168)=='using'
        token = wait_target(p)
        assert p.send('TARGETPOS', token, 3072)=='invalid'
        assert int(p.head[9])==4
        assert p.raw(f'{int(p.head[4])+1} {p.head[2]} TARGETPOS {token} 1077 2214 0')=='ok'
        settle(p)
        assert any(r[0]==168 for r in p.rows), 'Food must not be eaten by terrain'
        assert 'selection position 1077 2214 0' in (folder/'host.log').read_text()
        movement(p)
        p.send('USE', 168)
        token = wait_target(p)
        assert p.send('TARGET', token, 0)=='ok'
        settle(p)
        assert any(r[0]==168 for r in p.rows)
        p.send('USE', 168)
        token = wait_target(p)
        assert p.send('TARGET', token, 184)=='ok'
        settle(p)
        assert not any(r[0]==168 for r in p.rows)
        movement(p)
        p.close()
        print('Native location, invalid input, cancellation and feeding passed.', flush=True)


def client():
    run = runpy.run_path(str(Path(__file__).with_name('client-proof.py')))['run']
    run('world-target-client', 'Investigation', [
        'WAIT 900', 'USE 168', 'WAIT 400', 'TARGETING 1',
        'TARGETGROUND 538 1107', 'WAIT 400', 'TARGETING 0', 'PACKCHECK 168',
        'USE 168', 'WAIT 400', 'TARGETING 1', 'ESCAPE', 'WAIT 400', 'TARGETING 0',
        'USE 168', 'WAIT 400', 'TARGET 184', 'WAIT 400', 'ABSENT 168',
        'STEP 0', 'WAIT 500', 'WALKCHECK', 'EXIT',
    ], True, scenario='targets')


if __name__=='__main__':
    native()
    client()
