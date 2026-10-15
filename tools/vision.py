import base64
import requests
from config import VISION_MODEL, OLLAMA_URL
from tools.file_ops import _safe_path

# 支援的圖片副檔名（小寫），其他格式會被拒絕
SUPPORTED_FORMATS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}


def analyze_image_b64(image_b64: str, question: str) -> str:
    # 接受 base64 編碼的圖片字串（來自網頁拖拉上傳），直接送給視覺模型分析
    # 不需要本機路徑，由 agent_runner 在處理使用者上傳的圖片時呼叫
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={
                "model": VISION_MODEL,
                "messages": [{"role": "user", "content": question, "images": [image_b64]}],
                "stream": False,
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]
    except Exception as e:
        return f"圖片分析失敗（請確認 {VISION_MODEL} 已下載）：{e}"


def analyze_image(path: str, question: str = "請詳細描述這張圖片的內容") -> str:
    # 讀取本機圖片並透過視覺模型分析，回答關於圖片的問題
    # qwen3:8b 本身無視覺能力，此工具內部切換至 VISION_MODEL（llava:7b）處理，
    # 再將文字描述結果回傳給 qwen3 繼續使用
    try:
        p = _safe_path(path)
    except PermissionError as e:
        return str(e)

    if not p.exists():
        return f"檔案不存在：{p}"

    if p.suffix.lower() not in SUPPORTED_FORMATS:
        return f"不支援的圖片格式：{p.suffix}（支援：{', '.join(SUPPORTED_FORMATS)}）"

    # 將圖片二進位資料轉成 base64 字串，Ollama API 要求此格式
    try:
        image_b64 = base64.b64encode(p.read_bytes()).decode("utf-8")
    except Exception as e:
        return f"圖片讀取失敗：{e}"

    try:
        resp = requests.post(
            OLLAMA_URL,
            json={
                "model": VISION_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": question,
                        "images": [image_b64],
                    }
                ],
                "stream": False,
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]
    except Exception as e:
        return f"圖片分析失敗（請確認 {VISION_MODEL} 已透過 ollama pull 下載）：{e}"


# ── 工具定義（送給 Ollama 的 JSON Schema）──────────
# 注意：analyze_image_b64 不暴露給模型，只有 analyze_image 開放工具呼叫
# analyze_image_b64 是由 agent_runner 在前處理圖片時直接呼叫的內部函式
DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "analyze_image",
            "description": "分析本機圖片內容，可描述畫面、辨識文字、回答關於圖片的問題。內部使用視覺模型處理，支援 jpg/png/gif/bmp/webp",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "圖片的完整路徑",
                    },
                    "question": {
                        "type": "string",
                        "description": "想詢問圖片的問題，預設為「請詳細描述這張圖片的內容」",
                    },
                },
                "required": ["path"],
            },
        },
    },
]

# ── 工具實作對照表 ─────────────────────────────────
IMPLEMENTATIONS = {
    "analyze_image": analyze_image,
}
