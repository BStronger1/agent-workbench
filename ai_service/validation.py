import json, os, signal, subprocess, time
from pathlib import Path
from bs4 import BeautifulSoup

def static_errors(html, contract):
    soup=BeautifulSoup(html,'html.parser'); errors=[]
    if '<!doctype html' not in html.lower(): errors.append('Missing HTML doctype')
    for selector in ['title','h1','meta[name=viewport]']:
        if not soup.select_one(selector): errors.append('Missing '+selector)
    if soup.select('iframe,object,embed,form,base,meta[http-equiv],link,script[src]'): errors.append('External or embedded resources forbidden')
    for element in soup.select('[src],[href],[action]'):
        for attr in ['src','href','action']:
            v=element.get(attr,'').strip()
            if v and not v.startswith('#') and not (attr=='src' and element.name=='img' and v.startswith('data:image/')):
                errors.append('Resource must be inline')
    for text in contract['requiredTexts']:
        if text not in soup.get_text(): errors.append('Missing required text: '+text)
    if contract['checkInteraction']:
        for selector in ['button[data-testid=primary-action]','[data-testid=result]']:
            if not soup.select_one(selector): errors.append('Missing '+selector)
    return list(dict.fromkeys(errors))

class Validator:
    def __init__(self, data): self.data=Path(data)
    def __call__(self, run, number, html, contract):
        start=time.monotonic(); errors=static_errors(html,contract)
        attempt={'number':number,'html':html,'errors':errors,'browserStatus':'NOT_RUN','screenshot':None,'durationMs':0}
        if errors: return attempt
        command=json.loads(os.getenv('QA_COMMAND','[]'))
        if not command:
            attempt['browserStatus']='NOT_CONFIGURED'; return attempt
        task=self.data/'qa'/run/f'attempt-{number}'; task.mkdir(parents=True,exist_ok=True)
        (task/'index.html').write_text(html,encoding='utf-8')
        (task/'contract.json').write_text(json.dumps(contract,ensure_ascii=False),encoding='utf-8')
        try:
            process=subprocess.Popen([*command,str(task.resolve())],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=os.name!='nt')
            try: process.wait(timeout=45)
            except subprocess.TimeoutExpired:
                if os.name=='nt': subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
                else: os.killpg(process.pid,signal.SIGKILL)
                process.wait(); raise RuntimeError('Browser timeout')
            if process.returncode: raise RuntimeError('Browser infrastructure unavailable')
            attempt['errors']=json.loads((task/'result.json').read_text(encoding='utf-8'))['errors']
            attempt['browserStatus']='FAILED' if attempt['errors'] else 'PASSED'
            if (task/'screenshot.png').exists(): attempt['screenshot']=f'{run}/attempt-{number}/screenshot.png'
        except Exception:
            attempt['browserStatus']='ERROR'; attempt['errors']=['Browser infrastructure unavailable; no model repair']
        attempt['durationMs']=round((time.monotonic()-start)*1000)
        return attempt