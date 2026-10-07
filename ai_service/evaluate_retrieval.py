"""Small retrieval fixture measurement, not a general RAG benchmark."""
import json
from pathlib import Path
from ai_service.retrieval import embeddings, fuse, tokens
items=[
 {'id':'budget','title':'项目预算','excerpt':'本项目开发费用上限为五百元，超过预算必须停止新增支出。'},
 {'id':'style','title':'设计风格','excerpt':'页面使用绿色主题，白色背景，字体清晰，适合研究项目展示。'},
 {'id':'checklist','title':'清单操作','excerpt':'实验准备页面需要先勾选一项，再点击更新按钮，显示已完成一项。'},
 {'id':'security','title':'浏览器隔离','excerpt':'生成页面禁止联网请求、下载远程脚本和嵌入外部网页。'},
 {'id':'key','title':'模型配置','excerpt':'API 密钥按浏览器空间隔离，使用 AES-256-GCM 加密保存，接口不返回完整密钥。'},
 {'id':'qa','title':'验收流程','excerpt':'通过 Playwright 检查页面文本、执行按钮交互并保存截图，失败后反馈给模型修复。'}]
questions=[('最多可以花多少钱','budget'),('界面应该采用什么颜色','style'),('提交清单之前要做什么','checklist'),('能否加载互联网上的代码','security'),('用户的访问凭据如何保护','key'),('怎样验证生成的网页能够使用','qa')]
e=embeddings();vectors=e.embed_documents([r['title']+' '+r['excerpt'] for r in items]);results=[]
for query,expected in questions:
 v=e.embed_query(query)
 import numpy as np
 scores={r['id']:float(np.dot(v,d)/(np.linalg.norm(v)*np.linalg.norm(d))) for r,d in zip(items,vectors)}
 hybrid=fuse(query,items,scores)
 q=tokens(query);lex=sorted(items,key=lambda r:len(q&tokens(r['title']+' '+r['excerpt'])),reverse=True)
 lex=[r for r in lex if q&tokens(r['title']+' '+r['excerpt'])]
 results.append({'query':query,'expected':expected,'hybrid':[r['id'] for r in hybrid],'lexical':[r['id'] for r in lex[:8]],'cosine':scores})
report={'scope':'Six authored Chinese retrieval fixtures; real local ONNX embeddings; not held out, no LLM calls. Database isolation is tested separately in PostgreSQL integration tests.',
 'model':'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2','dimensions':384,'results':results,
 'hybridRecallAt3':sum(r['expected'] in r['hybrid'][:3] for r in results)/len(results),
 'lexicalRecallAt3':sum(r['expected'] in r['lexical'][:3] for r in results)/len(results)}
Path('evidence/retrieval-fixtures.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='results'},ensure_ascii=False))