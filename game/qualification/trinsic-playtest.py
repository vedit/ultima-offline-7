"""Original arrival-to-gate route through ClassicUO actions, widgets and targeting.

The native walkthrough supplies navigation/answers, not mutations. This adapter
has no connection to the native pipe and refuses commands without a UI route.
Debug/audit capabilities remain disabled. Each batch is acknowledged after the
client applies its native response, with bounded waits and an owned test save.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import shutil
import time

from investigation import Walkthrough
from play import BIN, HOST, client, session


def party_commands(serial):
    return ['SELF','PARTYOPEN',f'PARTYSELECT {serial} doll',f'PARTYSELECT {serial} pack','CAPTURE']


class FrontendPipe:
    def __init__(self, folder, future, host):
        self.path = folder / 'controls.txt'
        self.future, self.host, self.batch = future, host, 0
        self.journal = folder / 'frontend-commands.jsonl'
        self.action(['WAIT 700'], observation=True, timeout=145)

    def action(self, commands, *, observation=False, timeout=35):
        self.batch += 1
        request = self.path.with_suffix('.txt.request')
        tmp = request.with_suffix('.tmp')
        tmp.write_text(str(self.batch) + '\n' + '\n'.join(commands + [
            ('REPLYSYNC' if observation else 'REPLY') + ' ' + str(self.batch)]) + '\n')
        tmp.replace(request)
        end = time.monotonic() + timeout
        reply = self.path.with_suffix('.txt.reply.' + str(self.batch))
        while time.monotonic() < end:
            if self.future.done() or self.host.poll() is not None:
                raise RuntimeError(('Frontend exited', self.future.result() if self.future.done() else self.host.returncode, commands))
            try:
                number, frame = reply.read_text().split('\n', 1)
                if int(number) == self.batch:
                    reply.unlink()
                    self.frame = frame
                    lines = frame.splitlines()
                    self.head = lines[0].split()
                    self.rows = [list(map(int, line.split()[1:])) for line in lines if line.startswith('E ')]
                    self.choices = [bytes.fromhex(line[2:]).decode('latin1') for line in lines if line.startswith('A ')]
                    with self.journal.open('a') as out:
                        out.write(json.dumps(dict(batch=self.batch, actions=commands, header=lines[0])) + '\n')
                    return self.head[5]
            except (FileNotFoundError, PermissionError):
                pass
            time.sleep(.025)
        raise TimeoutError(('Frontend action', self.batch, commands, getattr(self, 'head', None)))

    def sync(self):
        return self.action([], observation=True)

    def send(self, op, a=0, b=0):
        if op == 'STEP':
            outcome = self.action([f'STEP {a}'])
            # ProcessKey accepts a step before the native action queue moves the
            # actor. Navigate from the next applied observation, not that ack.
            self.sync()
            return outcome
        if op == 'USE':
            return self.action([f'USE {a}'])
        if op == 'MOVE':
            return self.action([f'PICK {a}', f'DROP {b}'])
        if op in ('ANSWER', 'NUMBER'):
            assert a == int(self.head[10]), ('Stale native prompt', a, self.head)
            return self.action([f'{op} {b}'])
        if op == 'TARGET':
            assert a == int(self.head[10]) and self.head[9] == '4'
            return self.action([f'TARGET {b}'])
        if op == 'CLOSE':
            return self.action(['CLOSE', 'WAIT 250'], observation=True)
        if op == 'SAVE':
            return self.action(['U7SAVEKEY'], timeout=60)
        if op == 'BEGIN':
            return self.action(['BEGIN'])
        raise ValueError(('No player-input route', op, a, b))

    def capture(self):
        self.action(['CAPTURE'], observation=True)

    def close(self):
        # EXIT has no reply because it closes the client.
        self.batch += 1
        tmp = self.path.with_suffix('.txt.request.tmp')
        tmp.write_text(f'{self.batch}\nEXIT\n')
        tmp.replace(self.path.with_suffix('.txt.request'))


class FrontendWalkthrough(Walkthrough):
    def check(self, milestone):
        super().check(milestone)
        shutil.copyfile(self.folder/'GAME00.U7', self.folder/(milestone.replace(' ','-')+'.U7'))
        if milestone=='Spark witness':
            self.p.action(party_commands(self.actor(2)[0]), observation=True)
        self.p.capture()


def run(name):
    start = time.time()
    with session(name, 'Investigation', True, original_opening=True) as (folder, env, host):
        path = folder / 'controls.txt'
        path.write_text('')
        # This run owns these replay files; never touch another run's state.
        for suffix in ('.log', '.request', '.reply'):
            old = path.with_name(path.name + suffix)
            if old.exists():
                old.replace(folder / ('previous-' + str(time.time_ns()) + old.suffix))
        for old in folder.glob('controls.txt.reply.*'):
            old.replace(folder / ('previous-' + str(time.time_ns()) + old.name))
        env.update(TRINSIC_REPLAY=str(path), TRINSIC_REPLAY_LIVE='1', TRINSIC_ZOOM='1')
        with ThreadPoolExecutor(max_workers=1) as executor:
            running = executor.submit(client, folder, env, host, 1800)
            pipe = None
            try:
                pipe = FrontendPipe(folder, running, host)
                walk = FrontendWalkthrough(pipe, folder)
                walk.opening()
                walk.run(0)
                assert walk.xy()[0] > 1102 and walk.flags()[61]
                # Reload through the player's F9 key, then check continuity.
                pipe.action(['U7LOADKEY'])
                pipe.sync()
                assert walk.xy()[0] > 1102 and walk.flags()[61]
                pipe.capture()
                pipe.close()
                assert running.result(timeout=20) == 0
            finally:
                if pipe is not None and hasattr(pipe,'frame'):
                    (folder/'frontend-last-state.txt').write_text(pipe.frame)
                if not running.done():
                    if pipe is not None:
                        pipe.close()
                    try:
                        running.result(timeout=10)
                    except Exception:
                        if host.poll() is None:
                            host.terminate()
            images = []
            for image in sorted((BIN / 'Data/Client/Screenshots').glob('*.png')):
                if image.stat().st_mtime < start:
                    continue
                target = folder / f'journey-{len(images):02d}.png'
                shutil.copyfile(image, target)
                images.append(target.name)
            receipt = dict(run=name, status='passed', seconds=round(time.time()-start, 2),
                           original_opening=True, debug=False, audit=False,
                           host_sha256=hashlib.sha256(HOST.read_bytes()).hexdigest(),
                           client_sha256=hashlib.sha256((BIN/'cuo.dll').read_bytes()).hexdigest(),
                           batches=pipe.batch, milestones=walk.events, images=images,
                           limits='Uses frontend action/widget handlers; not OS pointer automation for every input.')
            (folder / 'frontend-journey.json').write_text(json.dumps(receipt, indent=2) + '\n')
            print(json.dumps({k: receipt[k] for k in ('run', 'status', 'seconds', 'batches', 'images')}, indent=2))
            return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', default='trinsic-frontend-journey')
    run(parser.parse_args().run)
