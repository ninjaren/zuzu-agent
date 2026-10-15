from datetime import datetime


def get_current_time() -> str:
    # 回傳目前系統的日期與時間（格式：YYYY-MM-DD HH:MM:SS）
    # 模型訓練資料有截止日期，任何需要「今天」的場景都應呼叫此工具
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ── 工具定義（送給 Ollama 的 JSON Schema）──────────
DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "取得目前的日期和時間",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

# ── 工具實作對照表 ─────────────────────────────────
IMPLEMENTATIONS = {
    "get_current_time": get_current_time,
}
