"""Export review candidates, never claim these are a validated fine-tuning dataset."""
import argparse, hashlib, json
from pathlib import Path

def candidates(report):
    for run in report.get('results',[]):
        if run.get('mode')!='live' or run.get('status')!='PASSED' or not run.get('attempts'): continue
        group=run.get('caseId',run['id'])
        yield {'group':group,'suggestedSplit':'validation' if int(hashlib.sha256(group.encode()).hexdigest()[:8],16)%5==0 else 'train',
               'reviewStatus':'pending_human_review','prompt':run['prompt'],'contract':{'requiredTexts':run.get('requiredTexts',[]),'steps':run.get('steps',[])},
               'response':{'html':run['attempts'][-1]['html']},'provenance':{'runId':run['id'],'model':run['model'],'workflow':run.get('workflow','legacy')}}
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('report');parser.add_argument('output');args=parser.parse_args()
    report=json.loads(Path(args.report).read_text(encoding='utf-8'))
    rows=list(candidates(report));out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
    print(json.dumps({'candidates':len(rows),'reviewRequired':True,'trainingPerformed':False}))