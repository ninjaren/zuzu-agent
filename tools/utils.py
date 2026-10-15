import requests
from datetime import datetime
from pathlib import Path

# QR Code 圖片存放目錄
QR_DIR = Path(r"F:\python_project\ai_agent\data\qrcodes")

# ip-api.com 免費端點，不需 Key，每分鐘 45 次限制
IP_API_URL = "http://ip-api.com/json/{ip}?lang=zh-TW&fields=status,message,country,regionName,city,isp,org,timezone,lat,lon,query"


def read_clipboard() -> str:
    # 讀取系統剪貼簿的文字內容，讓使用者可以直接貼文字進對話
    # 需要安裝：pip install pyperclip
    try:
        import pyperclip
        text = pyperclip.paste()
        if not text:
            return "剪貼簿目前是空的"
        preview = text[:200] + f"\n...（以下省略 {len(text) - 200} 字）" if len(text) > 200 else text
        return f"【剪貼簿內容】（共 {len(text)} 字）\n{preview}"
    except ImportError:
        return "缺少 pyperclip 套件，請先執行：pip install pyperclip"
    except Exception as e:
        return f"讀取剪貼簿失敗：{e}"


def create_qr_code(text: str, filename: str = "") -> str:
    # 將任意文字或網址產生成 QR Code PNG 圖片，存至 data/qrcodes/
    # 回傳圖片路徑，可搭配 analyze_image 確認內容
    # 需要安裝：pip install qrcode[pil]
    try:
        import qrcode
    except ImportError:
        return "缺少 qrcode 套件，請先執行：pip install qrcode[pil]"

    try:
        qr = qrcode.QRCode(
            version=None,           # 自動選最小版本
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(text)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        QR_DIR.mkdir(parents=True, exist_ok=True)
        if filename:
            # 去掉副檔名再補 .png，避免重複
            safe_name = Path(filename).stem + ".png"
        else:
            tag = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = f"qr_{tag}.png"

        out_path = QR_DIR / safe_name
        img.save(str(out_path))
        return str(out_path)

    except Exception as e:
        return f"QR Code 產生失敗：{e}"


def get_ip_info(ip: str = "") -> str:
    # 查詢 IP 地理位置資訊（ISP、國家、城市、時區）
    # 不填 ip 則查詢本機的對外公網 IP
    target = ip.strip() if ip.strip() else ""
    url = IP_API_URL.format(ip=target)

    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return f"IP 查詢失敗：{e}"

    if data.get("status") != "success":
        return f"IP 查詢失敗：{data.get('message', '未知錯誤')}（輸入：{ip or '本機 IP'}）"

    query_ip = data.get("query", ip or "本機 IP")
    country  = data.get("country", "N/A")
    region   = data.get("regionName", "N/A")
    city     = data.get("city", "N/A")
    isp      = data.get("isp", "N/A")
    org      = data.get("org", "")
    tz       = data.get("timezone", "N/A")
    lat      = data.get("lat", "N/A")
    lon      = data.get("lon", "N/A")

    lines = [
        f"【IP 資訊】{query_ip}",
        f"位置：{country} > {region} > {city}",
        f"ISP：{isp}" + (f"（{org}）" if org and org != isp else ""),
        f"時區：{tz}",
        f"座標：{lat}, {lon}",
    ]
    return "\n".join(l for l in lines if l.strip())


# ── 工具定義（送給 Ollama 的 JSON Schema）──────────
DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "read_clipboard",
            "description": (
                "讀取使用者系統剪貼簿的文字內容。當使用者說「我剪貼簿裡有…」"
                "或「幫我分析我剛複製的文字」時呼叫，避免使用者重複貼文字。"
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_qr_code",
            "description": (
                "將文字或網址產生成 QR Code PNG 圖片，回傳圖片路徑。"
                "適合需要將連結分享到手機、產生名片 QR Code 等場景。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "要編碼的文字或網址",
                    },
                    "filename": {
                        "type": "string",
                        "description": "輸出檔名（不含路徑，留空自動產生）",
                    },
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_ip_info",
            "description": (
                "查詢 IP 位址的地理位置、ISP 業者與時區資訊。"
                "不填 ip 則查詢本機對外 IP。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ip": {
                        "type": "string",
                        "description": "要查詢的 IP 位址，例如：8.8.8.8；留空查詢本機 IP",
                    },
                },
            },
        },
    },
]

# ── 工具實作對照表 ─────────────────────────────────
IMPLEMENTATIONS = {
    "read_clipboard": read_clipboard,
    "create_qr_code": create_qr_code,
    "get_ip_info":    get_ip_info,
}
