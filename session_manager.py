import json
from pathlib import Path
from config import SESSIONS_DIR

# 所有 session 的 metadata 集中存在這個檔案（id、title、建立時間）
META_FILE = SESSIONS_DIR / "_meta.json"


def load_meta() -> dict:
    # 讀取 metadata 檔案，回傳 {session_id: {id, title, created_at}} 的字典
    # 讀取失敗或檔案不存在時回傳空字典，讓呼叫方安全處理
    if META_FILE.exists():
        try:
            return json.loads(META_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_meta(meta: dict):
    # 將 metadata 字典序列化後寫回磁碟（ensure_ascii=False 保留中文字元）
    META_FILE.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def session_file(sid: str) -> Path:
    # 回傳指定 session 的對話紀錄檔路徑
    # 儲存策略：每個 session 一個獨立 JSON 檔（{sid}.json）
    # 所有 session 的標題與建立時間集中存在 _meta.json
    # 分開儲存的好處：列出 session 清單時只讀一個小 metadata 檔，不需載入全部對話紀錄
    return SESSIONS_DIR / f"{sid}.json"


def load_session(sid: str) -> list:
    # 讀取指定 session 的對話紀錄，格式為 [{role, content}, ...] 的列表
    # 檔案不存在或損毀時回傳空列表
    f = session_file(sid)
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def save_session(sid: str, msgs: list):
    # 將對話紀錄寫回磁碟，每次對話結束後呼叫以持久化紀錄
    session_file(sid).write_text(json.dumps(msgs, ensure_ascii=False, indent=2), encoding="utf-8")


def delete_session(sid: str):
    # 從 metadata 移除 session 紀錄，並刪除對應的對話紀錄檔
    meta = load_meta()
    meta.pop(sid, None)
    save_meta(meta)
    f = session_file(sid)
    if f.exists():
        f.unlink()
