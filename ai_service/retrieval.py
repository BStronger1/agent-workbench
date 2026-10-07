"""LangChain chunking, local multilingual embeddings, PostgreSQL hybrid retrieval."""
import hashlib, json, math, os, re, threading
from functools import lru_cache
import psycopg
from langchain_core.embeddings import Embeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

class LocalEmbeddings(Embeddings):
    def __init__(self):
        from fastembed import TextEmbedding
        self.model=TextEmbedding(model_name=os.getenv('EMBEDDING_MODEL','sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'),
            cache_dir=os.getenv('EMBEDDING_CACHE','runtime/embeddings'),threads=2)
    def embed_documents(self,texts): return [v.tolist() for v in self.model.passage_embed(texts)]
    def embed_query(self,text): return list(self.model.query_embed(text))[0].tolist()

@lru_cache(maxsize=1)
def embeddings(): return LocalEmbeddings()
def tokens(s):
    result=set(re.findall(r'[a-z0-9]+',s.lower()))
    for segment in re.findall(r'[\u4e00-\u9fff]+',s):
        result.update(segment[i:i+2] for i in range(max(1,len(segment)-1)))
    return result

def chunks(request):
    out=[]
    for m in request.memories:
        if m.get('active',True):
            out.append({'id':m['id'],'title':m.get('kind','memory')+' · '+m['key'],'excerpt':m['value'][:1500]})
    splitter=RecursiveCharacterTextSplitter(chunk_size=650,chunk_overlap=80,separators=['\n\n','\n','。','，',' ',''])
    for d in request.documents:
        if len(d['content'])>30000: raise ValueError('Document too long')
        for i,text in enumerate(splitter.split_text(d['content'])):
            out.append({'id':f'{d["id"]}:{i}','title':d['title'],'excerpt':text})
    if len(out)>1500: raise ValueError('Too many chunks')
    return out

def fuse(query, rows, vector_scores, threshold=0.45):
    q=tokens(query)
    lexical=sorted(((len(q & tokens(r['title']+' '+r['excerpt']))/max(1,len(q)),r['id']) for r in rows),reverse=True)
    lexical=[(score,id) for score,id in lexical if score>0]
    semantic=sorted(((score,id) for id,score in vector_scores.items() if score>=threshold),reverse=True)
    rank={}
    for ranking in [lexical,semantic]:
        for i,(_,id) in enumerate(ranking): rank[id]=rank.get(id,0)+1/(60+i+1)
    lookup={r['id']:r for r in rows}
    return [{**lookup[id],'score':score} for id,score in sorted(rank.items(),key=lambda x:(-x[1],x[0]))[:8]]

class VectorStore:
    def __init__(self, dsn, embed=None): self.dsn=dsn; self.embed=embed
    def search(self, request):
        items=chunks(request)
        embed=(self.embed or embeddings()) if items else None
        version=os.getenv('EMBEDDING_MODEL','sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
        with psycopg.connect(self.dsn) as c:
            c.execute('CREATE EXTENSION IF NOT EXISTS vector')
            c.execute('CREATE TABLE IF NOT EXISTS wb_chunks (owner text,project text,id text,title text,excerpt text,fingerprint text,embedding vector(384),PRIMARY KEY(owner,project,id))')
            c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(request.owner+'/'+request.projectId,))
            rows=c.execute('SELECT id,fingerprint FROM wb_chunks WHERE owner=%s AND project=%s',(request.owner,request.projectId)).fetchall()
            previous=dict(rows)
            pending=[]
            for r in items:
                r['fingerprint']=hashlib.sha256((version+r['title']+r['excerpt']).encode()).hexdigest()
                if previous.get(r['id'])!=r['fingerprint']: pending.append(r)
            vectors=embed.embed_documents([r['title']+'\n'+r['excerpt'] for r in pending]) if pending else []
            for r,v in zip(pending,vectors,strict=True):
                if len(v)!=384 or not all(math.isfinite(x) for x in v): raise ValueError('Invalid embedding')
                c.execute('INSERT INTO wb_chunks VALUES (%s,%s,%s,%s,%s,%s,%s::vector) ON CONFLICT(owner,project,id) DO UPDATE SET title=EXCLUDED.title,excerpt=EXCLUDED.excerpt,fingerprint=EXCLUDED.fingerprint,embedding=EXCLUDED.embedding',
                    (request.owner,request.projectId,r['id'],r['title'],r['excerpt'],r['fingerprint'],json.dumps(v)))
            c.execute('DELETE FROM wb_chunks WHERE owner=%s AND project=%s AND NOT(id=ANY(%s))',(request.owner,request.projectId,[r['id'] for r in items]))
            if not items: return []
            vector=embed.embed_query(request.query)
            found=c.execute('SELECT id,1-(embedding <=> %s::vector) FROM wb_chunks WHERE owner=%s AND project=%s ORDER BY embedding <=> %s::vector LIMIT 24',
                (json.dumps(vector),request.owner,request.projectId,json.dumps(vector))).fetchall()
        clean=[{k:v for k,v in r.items() if k!='fingerprint'} for r in items]
        return fuse(request.query,clean,dict(found),float(os.getenv('VECTOR_MIN_SCORE','0.45')))