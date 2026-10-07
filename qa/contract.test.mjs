import {test} from 'node:test';
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {executeSteps} from './contract.mjs';
test('checkbox prerequisite and exact assertion run in browser',async()=>{
 const b=await chromium.launch({headless:true,chromiumSandbox:process.platform==='linux'});
 try {
 const p=await b.newPage();p.setDefaultTimeout(1000);
 await p.setContent(`<h1>Checklist</h1><input type="checkbox" data-testid="selection-item"><button data-testid="primary-action">Update</button><p data-testid="result">0</p><script>document.querySelector('button').onclick=()=>document.querySelector('p').textContent=document.querySelector('input').checked?'1':'0'</script>`);
 await executeSteps(p,[{action:'check',target:'selection-item'},{action:'click',target:'primary-action'},{action:'assert_text',target:'result',value:'1'}]);
 await assert.rejects(executeSteps(p,[{action:'assert_text',target:'result',value:'10'}]));
 await assert.rejects(executeSteps(p,[{action:'click',target:'bad"] script'}]));
 } finally {await b.close();}
});