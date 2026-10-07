import {test} from 'node:test';
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {executeSteps} from './contract.mjs';
test('whitespace cannot fake a visible result change',async()=>{
 const browser=await chromium.launch({headless:true,chromiumSandbox:process.platform==='linux'});
 try {
 const page=await browser.newPage();
 await page.setContent('<button data-testid="primary-action">No-op</button><p data-testid="result">\n 0 \n</p>');
 await assert.rejects(executeSteps(page,[{action:'click',target:'primary-action'},{action:'assert_changed',target:'result'}]));
 } finally {await browser.close();}
});