"""Incorrect reports, partial progress, quiz failure/retry and exactly-once reward.

Start from a real frontend witness checkpoint. Only observer positioning is used;
the original dialogues, inventory operations, flags and save/load do the work.
"""
import argparse
import json
from pathlib import Path
import runpy
import shutil
import time

from baseline import actor
from investigation import Walkthrough
from play import ROOT, session
from reference import members, stage


def run(name, checkpoint):
    saved = members(checkpoint)
    assert saved['FLAGINIT'][64] and saved['FLAGINIT'][67] and not saved['FLAGINIT'][61]
    stage(name)
    folder = ROOT/'runs'/name
    shutil.copyfile(checkpoint, folder/'GAME00.U7')
    audit = runpy.run_path(str(Path(__file__).with_name('item-use-audit.py')))
    with session(name,'Investigation',False,{'TRINSIC_PREPARE':'interaction-audit'}) as (folder,env,host):
        p = audit['BoundedPipe'](env['TRINSIC_PIPE'],host)
        w = Walkthrough(p,folder)
        try:
            x,y,z=actor(saved,12)['xyz']
            assert p.raw(f'{int(p.head[4])+1} {p.head[2]} AUDITVISIT {x+1} {y} {z}')=='ok'
            audit['settle'](p)

            def checkpoint_flags():
                audit['settle'](p)
                assert p.send('SAVE')=='ok'
                return members(folder/'GAME00.U7')['FLAGINIT']

            def gold():
                # With no world container open, only party inventory is exported.
                return sum(r[9] for r in p.rows if r[1]==644 and r[6])

            before_gold=gold()
            w.talk(['murder','report','Yes','tailor'],12)
            assert not checkpoint_flags()[94]
            w.talk(['report','Yes','blacksmith','a key','a door'],12)
            flags=checkpoint_flags()
            assert flags[94] and flags[95] and not flags[96]
            assert p.send('LOAD')=='ok';p.sync()
            assert not w.flags()[61]

            normal_send=p.send
            wrong_numbers=[]
            def wrong_quiz(op,a=0,b=0):
                if op=='NUMBER':
                    low,high,step=map(int,next(l[2:] for l in p.frame.splitlines() if l.startswith('D ')).split())
                    b=next(value for value in range(low,high+1,step) if value!=b)
                    wrong_numbers.append(b)
                return normal_send(op,a,b)
            p.send=wrong_quiz
            try:
                w.talk(['report','Yes','a chest','all of these','Yes','hook','Crown Jewel','Yes'],12)
            finally:p.send=normal_send
            flags=checkpoint_flags()
            assert wrong_numbers and not flags[61] and flags[68]
            assert all(flags[i] for i in range(94,100))
            rewarded_gold=gold()
            assert rewarded_gold==before_gold+100,(before_gold,rewarded_gold)
            w.talk(['password','bye'],12)
            assert checkpoint_flags()[61]
            assert gold()==rewarded_gold,(gold(),rewarded_gold)
            assert p.send('LOAD')=='ok';p.sync()
            assert w.flags()[61]
            audit['movement'](p)
            result=dict(status='passed',source=str(checkpoint),wrong_report_rejected=True,
                        partial_report_saved=True,wrong_quiz_answers=wrong_numbers,
                        password_retry=True,reward_gold=rewarded_gold-before_gold,
                        reward_not_repeated=True,load_and_movement=True)
            (folder/'report-retry.json').write_text(json.dumps(result,indent=2)+'\n')
            print(json.dumps(result,indent=2))
            return result
        finally:p.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--run',default='trinsic-report-retry-'+time.strftime('%Y%m%d-%H%M%S'))
    parser.add_argument('--checkpoint',type=Path,required=True)
    args=parser.parse_args()
    run(args.run,args.checkpoint)
