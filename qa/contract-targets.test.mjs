import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {chromium} from 'playwright';
import {executeSteps,ContractError} from './contract.mjs';

test('real failed checklist reports target and match count without selecting the first match', async()=>{
 const report=JSON.parse(await readFile(new URL('../evidence/graph-live.json',import.meta.url),'utf8'));
 const run=report.results.find(r=>r.caseId==='G-02' && r.workflow==='graph_multi');
 const b=await chromium.launch({headless:true,chromiumSandbox:process.platform==='linux'});
 try{
  const p=await b.newPage();await p.setContent(run.attempts[0].html);
  await assert.rejects(executeSteps(p,run.steps),e=>e instanceof ContractError && /selection-item.*found 4/.test(e.message));
  assert.equal(await p.getByTestId('selection-item').evaluateAll(es=>es.filter(e=>e.checked).length),0);
 }finally{await b.close()}
});

test('unique checkbox targets retain group counting and exact assertions',async()=>{
 const b=await chromium.launch({headless:true,chromiumSandbox:process.platform==='linux'});
 try{
  const p=await b.newPage();
  await p.setContent(`<input class="item" type="checkbox" data-testid="selection-item"><input class="item" type="checkbox" data-testid="other-item"><button data-testid="primary-action">更新</button><p data-testid="result">已完成 0 项</p><script>document.querySelector('button').onclick=()=>document.querySelector('p').textContent='已完成 '+document.querySelectorAll('.item:checked').length+' 项'</script>`);
  const steps=[{action:'check',target:'selection-item'},{action:'click',target:'primary-action'},{action:'assert_text',target:'result',value:'已完成 1 项'}];
  await executeSteps(p,steps);
  await executeSteps(p,[{action:'check',target:'other-item'},{action:'click',target:'primary-action'},{action:'assert_text',target:'result',value:'已完成 2 项'}]);
  await assert.rejects(executeSteps(p,[{action:'assert_text',target:'result',value:'已完成 1 项'}]),/expected exact text.*已完成 1 项.*got.*已完成 2 项/);
  await p.evaluate(()=>document.body.insertAdjacentHTML('beforeend','<p data-testid="result">已完成 1 项</p>'));
  await assert.rejects(executeSteps(p,[{action:'assert_text',target:'result',value:'已完成 1 项'}]),/result.*found 2/);
 }finally{await b.close()}
});