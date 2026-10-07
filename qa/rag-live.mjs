import {request} from 'playwright';
import {mkdir,writeFile} from 'node:fs/promises';
if(!process.argv.includes('--live') || !process.env.EVAL_API_KEY) throw new Error('Explicit live mode and temporary credentials required');
const c=await request.newContext({baseURL:process.env.BASE_URL,extraHTTPHeaders:{'X-Requested-With':'workbench'}});
const report={timestamp:new Date().toISOString(),model:process.env.EVAL_MODEL,scope:'Two authored grounded-answer probes with real local embeddings, pgvector and the configured LLM. Not a held-out faithfulness benchmark.',results:[]};
async function api(path,data){const r=await c.post('/api/workbench'+path,{data,timeout:180000});if(!r.ok())throw new Error('API failed HTTP '+r.status());return r.json()}
let saved=false;
try{
 await c.get('/api/workbench/config');
 await api('/provider',{enabled:true,baseUrl:process.env.EVAL_BASE_URL,model:process.env.EVAL_MODEL,apiKey:process.env.EVAL_API_KEY,inputPrice:0,outputPrice:0});saved=true;
 const p=await api('/projects',{name:'真实 RAG 验证'});
 await api('/projects/'+p.id+'/documents',{title:'项目实施要求',content:'本项目开发费用上限为500元。API密钥必须采用AES-256-GCM加密保存，不能把完整密钥写入日志或返回前端。页面采用绿色主题。'});
 for(const q of [{query:'本项目开发费用上限是多少？',expected:'500'},{query:'API密钥需要用什么算法加密保存？',expected:'AES-256-GCM'}]){
  const started=Date.now();const r=await api('/projects/'+p.id+'/knowledge',{query:q.query,answer:true});
  const ids=new Set(r.sources.map(s=>s.id));
  const passed=r.answer.includes(q.expected) && r.citations.length>0 && r.citations.every(id=>ids.has(id));
  report.results.push({query:q.query,expected:q.expected,passed,durationMs:Date.now()-started,...r});
  console.log('RAG: '+(passed?'PASSED':'FAILED'));
 }
 report.status=report.results.every(r=>r.passed)?'passed':'completed_with_failures';
 if(report.status!=='passed')process.exitCode=1;
}catch(e){report.status='incomplete';report.error=e.message;process.exitCode=1;}
finally{
 if(saved){const r=await c.delete('/api/workbench/provider');if(!r.ok())throw new Error('Temporary key cleanup failed');}
 await mkdir(new URL('../evidence/',import.meta.url),{recursive:true});await writeFile(new URL('../evidence/rag-live.json',import.meta.url),JSON.stringify(report,null,2)+'\n');await c.dispose();
}