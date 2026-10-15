import requests
import chromadb
from pathlib import Path

# ── RAG（Retrieval-Augmented Generation）設定 ─────
# 使用 ChromaDB 儲存對話向量，nomic-embed-text 做語意嵌入
# 作用：讓模型能「回憶」過去相關對話，不只靠最近幾輪的短期記憶

# Ollama embedding API 端點
OLLAMA_EMBED_URL = "http://localhost:11434/api/embed"
# 嵌入模型，需透過 ollama pull nomic-embed-text 預先下載
EMBED_MODEL = "nomic-embed-text"

# 持久化向量資料庫，存放於專案目錄下的 chroma_db 資料夾
_client = chromadb.PersistentClient(path=str(Path(__file__).parent / "chroma_db"))
# 對話紀錄的向量集合，不存在時自動建立
_col = _client.get_or_create_collection("chat_history")


def _embed(text: str) -> list[float] | None:
    # 呼叫 Ollama embedding API 將文字轉成浮點數向量
    # 嵌入模型未就緒時回傳 None，呼叫方應跳過 RAG 而非拋出錯誤
    try:
        resp = requests.post(
            OLLAMA_EMBED_URL,
            json={"model": EMBED_MODEL, "input": text},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["embeddings"][0]
    except Exception:
        return None


def store_turn(turn_id: str, user: str, assistant: str):
    # 將一輪對話（使用者問題 + 模型回答）嵌入並存入向量資料庫
    # turn_id 格式為 "{session_id}_turn_{n}"，用 upsert 避免重複儲存
    vec = _embed(user)
    if vec is None:
        return  # embedding 模型未就緒，靜默跳過，不中斷主流程
    _col.upsert(
        ids=[turn_id],
        documents=[f"Q: {user}\nA: {assistant}"],
        embeddings=[vec],
        metadatas=[{"user": user, "assistant": assistant}],
    )


def retrieve(query: str, top_k: int = 3) -> list[dict]:
    # 用語意搜尋找出與目前問題最相關的過去對話，供 agent_runner 注入 context
    # 回傳格式：[{"user": "...", "assistant": "..."}, ...]
    count = _col.count()
    if count == 0:
        return []  # 資料庫是空的，直接跳過
    vec = _embed(query)
    if vec is None:
        return []  # embedding 模型未就緒，跳過 RAG
    results = _col.query(
        query_embeddings=[vec],
        n_results=min(top_k, count),  # 避免請求數量超過實際資料筆數
    )
    return [
        {"user": meta["user"], "assistant": meta["assistant"]}
        for meta in results["metadatas"][0]
    ]


def clear_all():
    # 清空所有對話向量紀錄（刪除並重建集合）
    # 主要用於測試或重置，正常使用不需呼叫
    _client.delete_collection("chat_history")
    global _col
    _col = _client.get_or_create_collection("chat_history")
