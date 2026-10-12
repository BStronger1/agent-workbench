import assert from 'node:assert/strict';
import { chromium } from 'playwright';
import { mkdir } from 'node:fs/promises';

// UI contract test: mock the API, never call a model or change a user's projects.
const browser = await chromium.launch({headless:true});
try {
  const context = await browser.newContext();
  const page = await context.newPage();
  const project = {id:'skill-ui-fixture',name:'技能界面回归',memories:[],documents:[],runs:[]};
  const requests = [];
  await page.route('**/api/workbench/**', async route => {
    const path = new URL(route.request().url()).pathname.replace('/api/workbench','');
    let response;
    if (path === '/config') response = {mode:'live',aiEnabled:true,modelConfigured:true,browserValidation:true,liveAccessRequired:false};
    else if (path === '/projects') response = [project];
    else if (path.endsWith('/runs') && route.request().method() === 'POST') {
      const body = route.request().postDataJSON();
      requests.push(body);
      const run = {
        id:'skill-ui-run-'+requests.length,prompt:body.prompt,mode:'live',model:'ui-fixture',
        workflow:body.workflow,skillsEnabled:body.skillsEnabled,status:'PASSED',
        createdAt:new Date().toISOString(),attempts:[],memorySources:[],events:[],
        durationMs:10,inputTokens:0,outputTokens:0,usageKnown:true,maxRepairs:1,
        skillTrace:body.skillsEnabled ? [{attempt:0,name:'web-ui-acceptance-repair',version:'1.0.0',
          references:['references/state.md'],contextChars:100,reason:'interaction_failure',contractHash:'fixture'}] : [],
      };
      project.runs.push(run);
      response=run;
    } else if (path === '/projects/'+project.id) response=project;
    else throw new Error('Unexpected UI request: '+path);
    await route.fulfill({contentType:'application/json',body:JSON.stringify(response)});
  });
  await page.goto(process.env.BASE_URL || 'http://127.0.0.1:8123');
  await page.getByLabel('执行方式').selectOption('graph_single');
  const toggle=page.getByLabel('交互失败时使用修复技能');
  assert.equal(await toggle.isChecked(),true);
  await toggle.uncheck();
  await page.getByRole('button',{name:'开始生成与验证'}).click();
  await page.getByRole('button',{name:'过程',exact:true}).click();
  await page.getByTestId('skill-trace').waitFor();
  assert.match(await page.getByTestId('skill-trace').textContent(),/已关闭/);
  assert.equal(requests[0].skillsEnabled,false);
  await toggle.check();
  await page.getByRole('button',{name:'开始生成与验证'}).click();
  await page.waitForFunction(()=>document.querySelector('[data-testid=skill-trace]')?.textContent.includes('web-ui-acceptance-repair'));
  assert.equal(requests[1].skillsEnabled,true);
  assert.match(await page.getByTestId('skill-trace').textContent(),/1\.0\.0/);
  await mkdir('qa/test-results',{recursive:true});
  await page.screenshot({path:'qa/test-results/skills-ui.png',fullPage:true});
  await context.close();
  console.log('Skill UI: default, off/on propagation and version trace passed (mock API; zero model calls).');
} finally {
  await browser.close();
}
