"""Loopback-only internal API; Spring Boot remains the ownership boundary."""
import hmac, os, threading, uuid
from pathlib import Path
from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from .models import RunInput, KnowledgeInput, Answer
from .journal import Journal
from .llm import Model
from .graph import execute
from .validation import Validator
from .retrieval import VectorStore
os.environ['LANGSMITH_TRACING']='false'
os.environ['LANGCHAIN_TRACING_V2']='false'
app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
data=Path(os.getenv('WORKBENCH_DATA','data')).resolve()
ai_data=data/'ai'; ai_data.mkdir(parents=True,exist_ok=True)
journal=Journal(ai_data/'calls.sqlite')
slots=threading.BoundedSemaphore(2)
lock_guard=threading.Lock(); active=set()

def authorize(x_ai_token: str=Header(default='')):
    token=os.getenv('AI_SERVICE_TOKEN','')
    if len(token)<32 or not hmac.compare_digest(token,x_ai_token): raise HTTPException(403,'Internal authentication required')
@app.exception_handler(RequestValidationError)
async def invalid(request, error):
    return JSONResponse(status_code=422,content={'detail':'Invalid AI request contract'})
@app.get('/health',dependencies=[Depends(authorize)])
def health():
    return {'ok':True,'engine':'langgraph','vectorConfigured':bool(os.getenv('VECTOR_DSN'))}
@app.post('/runs',dependencies=[Depends(authorize)])
def run(request:RunInput):
    key=(request.owner,request.projectId,request.runId)
    with lock_guard:
        if key in active: raise HTTPException(409,'Run already active')
        if not slots.acquire(blocking=False): raise HTTPException(429,'AI service busy')
        active.add(key)
    try:
        model=Model(request.credentials,journal,request.runId,request.tokenBudget)
        return execute(request,ai_data,model,Validator(data),journal)
    except Exception:
        raise HTTPException(400,'AI request failed; check configuration and checkpoint') from None
    finally:
        with lock_guard: active.remove(key)
        slots.release()
@app.post('/knowledge',dependencies=[Depends(authorize)])
def knowledge(request:KnowledgeInput):
    dsn=os.getenv('VECTOR_DSN','')
    if not dsn: raise HTTPException(503,'Vector database not configured')
    if not slots.acquire(blocking=False): raise HTTPException(429,'AI service busy')
    try:
        sources=VectorStore(dsn).search(request)
        result={'method':'hybrid-pgvector-rrf','sources':sources,'answer':'未找到足够相关的项目资料，请补充资料或调整问题。','citations':[]}
        if sources:
            result['answer']='\n\n'.join('['+s['id']+'] '+s['excerpt'] for s in sources)
        if request.answer and sources:
            if request.credentials is None: raise ValueError('Model required for RAG')
            run_id=str(uuid.uuid4())
            model=Model(request.credentials,journal,run_id,20000)
            reply=model.call('rag','Answer in Chinese using ONLY the supplied evidence. Cite evidence IDs in square brackets. If evidence cannot answer, say so and return empty citations. Never invent source IDs.',{'question':request.query,'sources':sources},Answer,1200)
            valid={s['id'] for s in sources}
            if not set(reply['citations']).issubset(valid) or (not reply['citations'] and reply['answer']):
                result['answer']='证据不足或引用校验未通过，以下列原文为准。'
            else: result.update(reply)
            result['usage']=journal.usage(run_id)
            result['method']='rag-hybrid-pgvector-rrf'
        return result
    except Exception:
        raise HTTPException(503,'Retrieval or answer generation failed; no silent lexical fallback') from None
    finally: slots.release()