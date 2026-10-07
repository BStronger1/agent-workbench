import os, uuid
import pytest
from ai_service.models import KnowledgeInput
from ai_service.retrieval import VectorStore


class Embed:
    def embed_documents(self, texts):
        return [[1.0] + [0.0] * 383 for _ in texts]

    def embed_query(self, text):
        return [1.0] + [0.0] * 383


@pytest.mark.skipif(
    not os.getenv("VECTOR_DSN"), reason="Requires real PostgreSQL with pgvector"
)
def test_pgvector_isolation_update_deactivation():
    import psycopg

    project = str(uuid.uuid4())
    owner = uuid.uuid4().hex * 2
    store = VectorStore(os.environ["VECTOR_DSN"], Embed())
    r = KnowledgeInput(
        owner=owner,
        projectId=project,
        query="budget",
        memories=[{"id": "memory", "key": "budget", "value": "200", "active": True}],
    )
    try:
        assert store.search(r)[0]["excerpt"] == "200"
        other = r.model_copy(deep=True)
        other.owner = "b" * 64
        other.memories = []
        assert store.search(other) == []
        r.memories[0]["value"] = "300"
        assert store.search(r)[0]["excerpt"] == "300"
        r.memories[0]["active"] = False
        assert store.search(r) == []
        with psycopg.connect(store.dsn) as c:
            assert (
                c.execute(
                    "SELECT count(*) FROM wb_chunks WHERE owner=%s AND project=%s",
                    (owner, project),
                ).fetchone()[0]
                == 0
            )
    finally:
        with psycopg.connect(store.dsn) as c:
            c.execute("DELETE FROM wb_chunks WHERE project=%s", (project,))


@pytest.mark.skipif(
    not os.getenv("VECTOR_DSN") or os.getenv("RUN_EMBEDDING_TESTS") != "1",
    reason="Opt-in real embeddings + pgvector",
)
def test_real_embeddings_with_pgvector():
    import psycopg

    project = str(uuid.uuid4())
    owner = uuid.uuid4().hex * 2
    store = VectorStore(os.environ["VECTOR_DSN"])
    r = KnowledgeInput(
        owner=owner,
        projectId=project,
        query="用户的访问凭据如何保护",
        memories=[
            {
                "id": "key",
                "key": "模型配置",
                "value": "API 密钥按浏览器空间隔离，使用 AES-256-GCM 加密保存，接口不返回完整密钥。",
                "active": True,
            },
            {
                "id": "style",
                "key": "页面风格",
                "value": "页面采用绿色背景和圆角按钮。",
                "active": True,
            },
        ],
    )
    try:
        sources = store.search(r)
        assert sources and sources[0]["id"] == "key"
    finally:
        with psycopg.connect(store.dsn) as c:
            c.execute("DELETE FROM wb_chunks WHERE project=%s", (project,))
