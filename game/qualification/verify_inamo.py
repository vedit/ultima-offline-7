"""Capture Inamo in the playable stable and hit-test his compiled sprite."""
import runpy
import struct
from pathlib import Path

from investigation import DOORS, Walkthrough
from play import Pipe, session
from town_atlas import COMPACT


def verify():
    name = 'inamo-wall-proof'
    with session(name, 'Investigation', True) as (folder, env, host):
        pipe = Pipe(env['TRINSIC_PIPE'], host)
        try:
            walk = Walkthrough(pipe, folder)
            walk.go((1070, 2208))
            door = next(r for r in pipe.rows if r[1] in DOORS and r[3:5] == [1071, 2207])
            if door[2] % 4 != 1:
                pipe.send('USE', door[0])
            walk.go((1070, 2207))
            walk.go((1069, 2197))
            victim = next(r for r in pipe.rows if r[1:6] == [414, 26, 1066, 2182, 0])
            assert pipe.send('SAVE') == 'ok'
        finally:
            pipe.close()
    frames = (line.split() for line in (COMPACT/'graphics.tsv').read_text().splitlines())
    graphic = next(g for s, f, g in frames if (s, f) == ('414', '26'))
    data = (COMPACT/'Art/Statics'/f'{graphic}.art').read_bytes()
    width, height = struct.unpack_from('<HH', data, 4)
    assert height > width
    replay = runpy.run_path(str(Path(__file__).with_name('client-proof.py')))['run']
    result = replay(name, 'Investigation', ['WAIT 3500', 'CAPTURE', f'PIXELUSE {victim[0]} 55', 'EXIT'],
                    False, scenario='inamo')
    assert any(f'on {width}x{height} sprite' in line for line in result['events'])
    assert len(result['images']) == 1
    print(folder/result['images'][0])


if __name__ == '__main__':
    verify()
