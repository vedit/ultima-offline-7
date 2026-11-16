"""Capture the original U7 renderer and ClassicUO from identical private saves."""
import argparse
import json
import os
import runpy
import shutil
import subprocess
from pathlib import Path

from PIL import Image
from play import HOST, ROOT, Pipe, copy_test_save, session
from reference import members, sha
from baseline import actor

HERE = Path(__file__).resolve().parent
VIEWS = [('barn-overview', (1070, 2188, 0), '0.7', 3),
         ('barn-detail', (1068, 2201, 0), '0.5', 2)]


def capture(source_run, prefix, output, town):
    output.mkdir(parents=True, exist_ok=True)
    debug = runpy.run_path(str(HERE / 'developer-wand.py'))
    replay = runpy.run_path(str(HERE / 'client-proof.py'))['run']
    pairs = []
    for label, position, zoom, direction in VIEWS:
        run = prefix + '-' + label
        copy_test_save(source_run, run)  # Refuses an existing run; never touches the source save.
        with session(run, 'Investigation', False,
                     {'TRINSIC_PREPARE': 'interaction-audit', 'TRINSIC_DEBUG': '1'}) as (folder, env, host):
            pipe = Pipe(env['TRINSIC_PIPE'], host)
            try:
                checks = debug['Checks'](pipe)
                checks.send('AUDITVISIT', position[0], position[1], str(position[2]))
                debug['audit']['settle'](pipe)
                checks.send('TURN', direction)
                assert pipe.send('SAVE') == 'ok'
                avatar = actor(members(folder / 'GAME00.U7'), 0)
                assert avatar['name'] == 'Vedit', avatar['name']
                assert avatar['xyz'] == list(position), avatar['xyz']
            finally:
                pipe.close()
        checkpoint = sha(folder / 'GAME00.U7')
        for name, data in members(folder / 'GAME00.U7').items():
            (folder / 'GAMEDAT' / name).write_bytes(data)
        original_env = dict(os.environ, U7_TEST_INPUT='6000 shot barn-original.ppm; 6500 quit')
        for name in ('TRINSIC_PIPE', 'TRINSIC_TOWN', 'TRINSIC_READY'):
            original_env.pop(name, None)
        with (folder / 'original-render.log').open('w') as log:
            result = subprocess.run([str(HOST), '--data', str(folder), '--program', 'u7', '-p'],
                                    cwd=folder, env=original_env, stdout=log, stderr=log, timeout=45)
        assert result.returncode == 0, result.returncode
        original = output / (label + '-u7.png')
        with Image.open(folder / 'barn-original.ppm') as image:
            image.convert('RGB').save(original)  # Lossless encoding only; no crop or retouch.
        result = replay(run, 'Investigation', ['WAIT 3000', 'CAPTURE', 'EXIT'], False,
                        zoom=zoom, scenario=label, extra={'TRINSIC_TOWN': str(town)})
        assert len(result['images']) == 1, result
        current = output / (label + '-uo7.png')
        shutil.copyfile(folder / result['images'][0], current)
        assert sha(folder / 'GAME00.U7') == checkpoint
        pair = {'id': label, 'position': position, 'avatar': 'Vedit', 'uo7_zoom': zoom,
                'shared_checkpoint_sha256': checkpoint,
                'original_renderer': 'Portable original Ultima VII renderer with original game assets',
                'current_renderer': 'ClassicUO with approved Christopher artwork and Party button',
                'files': {p.name: {'sha256': sha(p), 'size': list(Image.open(p).size)}
                          for p in (original, current)}}
        pairs.append(pair)
        (output / 'barn-captures.json').write_text(json.dumps({'pairs': pairs}, indent=2) + '\n')
        print(json.dumps(pair), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-run', required=True, help='Existing saved scene with Avatar named Vedit')
    parser.add_argument('--run-prefix', required=True, help='Unique prefix for two disposable copied saves')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--town', type=Path, default=ROOT / 'town-battlement-data')
    args = parser.parse_args()
    capture(args.source_run, args.run_prefix, args.output.resolve(), args.town.resolve())
