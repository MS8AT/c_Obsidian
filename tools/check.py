"""Repeatable local verification. Reports contain results, never credentials."""
from pathlib import Path
import argparse
import datetime
import json
import re
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    results=[]
    def run(name,command):
        result=subprocess.run(command,cwd=ROOT,capture_output=True,encoding='utf-8',errors='replace')
        results.append({'name':name,'result':'PASS' if result.returncode==0 else 'FAIL','output':result.stdout+result.stderr})
        if result.returncode:
            print(result.stdout+result.stderr)
            raise SystemExit(result.returncode)
    run('API CLI security regression suite',[sys.executable,'-B','-m','unittest','discover','-s','tests','-v'])
    for name in ['app.js','login.js']:
        run('JavaScript '+name,['node','--check','web/'+name])
    js=(ROOT/'web/app.js').read_text(encoding='utf-8').split('let lang=')[0]
    js+="\nconst keys=Object.keys(I18N.en);for(const l of ['ru','en','zh']){for(const k of keys){if(!I18N[l][k])throw Error(l+':'+k);}}console.log(JSON.stringify({languages:3,keys:keys.length,result:'PASS'}));"
    run('Translation coverage',['node','-e',js])
    for path in ROOT.rglob('*.py'):
        if '.git' not in path.parts:compile(path.read_text(encoding='utf-8'),str(path),'exec')
    results.append({'name':'All Python sources compile','result':'PASS'})
    report={'checked_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'Local source, API, CLI; container and external deployment tracked separately','checks':results}
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'result':'PASS','checks':len(results),'report':str(args.report) if args.report else None}))


if __name__=='__main__':main()
