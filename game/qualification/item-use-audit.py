"""Audit original Trinsic interactions in a private save, with bounded native waits."""
import argparse
import csv
import json
import queue
import runpy
import struct
import threading
import time
from pathlib import Path
from investigation import Walkthrough, distance
from play import Pipe, ROOT, session
from install_paths import ATLAS_OUTPUT


class BoundedPipe(Pipe):
    def __init__(self, name, host):
        self.host = host
        self.requests = queue.Queue()
        self.answers = queue.Queue()
        def worker():
            while True:
                msg = self.requests.get()
                try:
                    if msg == '0 0 SCREEN':
                        self.file.write(msg.encode())
                        answer = self.file.read(131072).decode()
                    else:
                        answer = super(BoundedPipe, self).raw(msg)
                    self.answers.put((True, answer))
                except Exception as error:
                    self.answers.put((False, error))
        threading.Thread(target=worker, daemon=True).start()
        super().__init__(name, host)

    def raw(self, msg):
        self.requests.put(msg)
        try:
            ok, result = self.answers.get(timeout=6)
        except queue.Empty:
            self.host.terminate()
            raise TimeoutError(f"Native interaction did not answer: {msg}")
        if not ok:
            raise result
        return result


def settle(p):
    prompts = []
    quiet = None
    for _ in range(100):
        time.sleep(.025)
        p.sync()
        mode, token = map(int, p.head[9:11])
        if mode:
            prompts.append(mode)
            quiet = None
        if mode == 4:
            p.send('TARGET', token, 0)
        elif mode in (1, 2):
            # Decline commitments, or end dialogue through the original offered choice.
            answer = next((i for word in ('bye', 'no') for i, text in enumerate(p.choices)
                           if text.lower() == word), 0)
            p.send('ANSWER', token, answer)
        elif mode == 3:
            low = int(next(line for line in p.frame.splitlines() if line.startswith('D ')).split()[1])
            p.send('NUMBER', token, low)
        elif mode == 6:
            p.send('DISMISS', token)
        elif mode == 5:
            # SCREEN is read-only and does not alter sequence or the outstanding prompt.
            frame = p.raw('0 0 SCREEN').split()
            assert frame[0] == 'F' and len(frame[3]) == 1536 and len(frame[4]) == int(frame[1])*int(frame[2])*2
            p.send('DISMISS', token)
        elif int(p.head[8]):
            p.send('CLOSE')
        else:
            health = list(map(int, next(line for line in p.frame.splitlines() if line.startswith('H ')).split()[1:]))
            if all(health[i] == 0 for i in (0, 3, 4, 5, 7)):
                if quiet is None: quiet = time.monotonic()
                if time.monotonic()-quiet >= .3:
                    return prompts, health
            else:
                quiet = None
    raise TimeoutError(('Interaction never returned', p.head, prompts))


def movement(p):
    avatar = lambda: next(r for r in p.rows if r[7] == 0)
    start = avatar()[3:6]
    for direction in range(8):
        outcome = p.send('STEP', direction)
        if outcome == 'modal':
            settle(p)  # Original scheduled Usecode can request a target on the next world tick.
            outcome = p.send('STEP', direction)
        assert outcome not in ('modal', 'busy', 'movement-held', 'invalid'), (outcome, p.head)
        settle(p)
        if avatar()[3:6] != start:
            settle(p)
            return
    raise AssertionError(('No direction allowed movement', start))


def audit(town=False):
    name = 'town-item-matrix' if town else 'inventory-item-audit'
    report = {'scope': 'native Usecode dispatch, modal completion/cancellation, and movement',
              'limits': 'One instance per town shape; target prompts are cancelled. This is not every quest outcome.',
              'positioning': 'Qualification-only observer teleport' if town else 'Normal movement from use position',
              'passed': [], 'unreached': []}
    with session(name, 'Investigation', True, {'TRINSIC_PREPARE': 'interaction-audit'} if town else None) as (folder, env, host):
        p = BoundedPipe(env['TRINSIC_PIPE'], host)
        def receipt():
            (folder/'interaction-audit.json').write_text(json.dumps(report, indent=2))
        def exercise(row):
            label = [row[0], row[1], row[2], *row[3:6]]
            assert p.send('SAVE') == 'ok'
            before_feedback = set(line for line in p.frame.splitlines() if line.startswith(('B ', 'R ')))
            print('USE', label, flush=True)
            outcome = p.send('USE', row[0])
            prompts, health = settle(p)
            feedback = [line for line in p.frame.splitlines() if line.startswith(('B ', 'R ')) and line not in before_feedback]
            # Town fixtures can be on counters or behind walls. Verify control at a known
            # clear road after use; inventory tests walk directly from the use position.
            if town:
                assert p.raw(f'{int(p.head[4])+1} {p.head[2]} AUDITVISIT 1076 2214 0') == 'ok'
            movement(p)
            assert p.send('LOAD') == 'ok'
            p.sync()
            report['passed'].append({'item': label, 'outcome': outcome, 'prompts': prompts, 'health': health, 'feedback': feedback})
            receipt()
        try:
            if not town:
                # Observer positioning must never be available in a normal play session.
                before = next(r[3:6] for r in p.rows if r[7] == 0)
                assert p.raw(f'{int(p.head[4])+1} {p.head[2]} AUDITVISIT 1077 2214 0') == 'invalid'
                assert next(r[3:6] for r in p.rows if r[7] == 0) == before
                candidates = [r[:] for r in p.rows if r[6] in (56, 88, 184, 200)]
                for row in candidates:
                    exercise(row)
            else:
                link = (folder/'STATIC/LINKDEP1').read_bytes()
                types = (folder/'STATIC/TFA.DAT').read_bytes()
                refs = list(csv.DictReader((ATLAS_OUTPUT/'references.csv').open(encoding='utf-8-sig')))
                candidates = {}
                for ref in refs:
                    shape = int(ref['shape'])
                    if ref['layer'] not in ('World object', 'Fixed', 'Contained'):
                        continue
                    scripted = shape*4+4 <= len(link) and struct.unpack_from('<H', link, shape*4+2)[0] != 65535
                    container = (types[shape*3+1] & 15) == 6
                    if not scripted and not container:
                        continue
                    candidates.setdefault(shape, []).append(ref)
                walk = Walkthrough(p, folder)
                while candidates:
                    shape = min(candidates, key=lambda s:min(distance(walk.xy(), (int(r['x']), int(r['y']))) for r in candidates[s]))
                    refs = sorted(candidates.pop(shape), key=lambda r:distance(walk.xy(), (int(r['x']), int(r['y']))))
                    errors = []
                    for ref in refs:
                        xy = (int(ref['x']), int(ref['y']))
                        try:
                            floor = 6 if int(ref['lift']) >= 6 else 0
                            assert p.raw(f'{int(p.head[4])+1} {p.head[2]} AUDITVISIT {xy[0]+1} {xy[1]+1} {floor}') == 'ok'
                            settle(p)
                            parents = {r[0]:tuple(r[3:5]) for r in p.rows if not r[6]}
                            row = next(r for r in p.rows if r[1] == shape and
                                       (parents.get(r[6]) if ref['layer']=='Contained' else tuple(r[3:5])) == xy)
                            exercise(row)
                            break
                        except (RuntimeError, StopIteration) as error:
                            errors.append([xy, str(error)])
                    else:
                        report['unreached'].append({'shape': shape, 'attempts': errors})
                        receipt()
            print(json.dumps({'passed': len(report['passed']), 'unreached': report['unreached']}), flush=True)
        finally:
            receipt()
            p.close()


def client():
    run = runpy.run_path(str(Path(__file__).with_name('client-proof.py')))['run']
    run('original-map-client', 'Investigation', [
        'WAIT 1100', 'USE 104', 'WAIT 400', 'MODAL 5', 'CAPTURE',
        'DISMISS', 'WAIT 400', 'MODAL 0', 'STEP 0', 'WAIT 500',
        'USE 104', 'WAIT 350', 'MODAL 5', 'ESCAPE', 'WAIT 350', 'MODAL 0',
        'STEP 4', 'WAIT 500', 'WALKCHECK',
        'USE 11648', 'WAIT 400', 'MODAL 5', 'CAPTURE', 'ESCAPE',
        'WAIT 350', 'MODAL 0', 'STEP 0', 'WAIT 500', 'WALKCHECK', 'CAPTURE', 'EXIT',
    ], True, scenario='map')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--town', action='store_true')
    parser.add_argument('--client', action='store_true')
    args = parser.parse_args()
    if args.client:
        client()
    else:
        audit(args.town)
