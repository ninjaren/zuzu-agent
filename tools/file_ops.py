import os
import csv
from pathlib import Path

# 所有檔案操作只允許在此目錄內，防止路徑穿越攻擊
WORKSPACE = Path(r"F:\python_project\ai_agent")


def _safe_path(path: str) -> Path:
    # 將傳入路徑解析為絕對路徑，並確認在 WORKSPACE 範圍內
    # 加 os.sep 是為了避免誤判：例如 "ai_agent" 是 "ai_agentXXX" 的前綴，
    # 但後者不是合法子路徑，加上路徑分隔符才能正確防堵
    p = Path(path).resolve()
    workspace = WORKSPACE.resolve()
    if p != workspace and not str(p).startswith(str(workspace) + os.sep):
        raise PermissionError(f"路徑超出允許範圍：{p}（只允許 {WORKSPACE}）")
    return p


def list_files(path: str = "") -> str:
    # 列出資料夾內容（先列子目錄、再列檔案，各自按名稱排序）
    # 不傳 path 則列出 WORKSPACE 根目錄
    try:
        p = _safe_path(path) if path else WORKSPACE
        if not p.is_dir():
            return f"不是資料夾：{p}"
        items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
        lines = [f"{'[目錄]' if i.is_dir() else '[檔案]'} {i.name}" for i in items]
        return f"{p}\n" + "\n".join(lines) if lines else "（空資料夾）"
    except PermissionError as e:
        return str(e)
    except Exception as e:
        return f"列出失敗：{e}"


def read_file(path: str) -> str:
    # 讀取文字檔案的全部內容，以 UTF-8 編碼讀取
    try:
        return _safe_path(path).read_text(encoding="utf-8")
    except PermissionError as e:
        return str(e)
    except Exception as e:
        return f"讀取失敗：{e}"


def write_file(path: str, content: str) -> str:
    # 建立新檔案或完整覆寫現有內容
    # 父資料夾不存在時自動建立（含多層子目錄）
    try:
        p = _safe_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"已寫入：{p}"
    except PermissionError as e:
        return str(e)
    except Exception as e:
        return f"寫入失敗：{e}"


def append_file(path: str, content: str) -> str:
    # 在現有檔案末尾附加內容，不覆蓋原有資料
    # 檔案不存在時自動建立（行為同 write_file）
    try:
        p = _safe_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(content)
        return f"已附加至：{p}"
    except PermissionError as e:
        return str(e)
    except Exception as e:
        return f"附加失敗：{e}"


def delete_file(path: str) -> str:
    # 永久刪除指定檔案（不可復原，請確認後再呼叫）
    # 僅允許刪除檔案，不能刪除整個目錄
    try:
        p = _safe_path(path)
        if not p.exists():
            return f"檔案不存在：{p}"
        if p.is_dir():
            return f"這是目錄，不能用 delete_file 刪除：{p}"
        p.unlink()
        return f"已刪除：{p}"
    except PermissionError as e:
        return str(e)
    except Exception as e:
        return f"刪除失敗：{e}"


def read_csv(path: str, max_rows: int = 50) -> str:
    # 讀取 CSV 檔案並回傳結構化摘要（欄位名稱、資料筆數、前 N 行預覽）
    # 自動嘗試 UTF-8 → Big5（台灣券商常見編碼）→ CP950
    try:
        p = _safe_path(path)
        if not p.exists():
            return f"檔案不存在：{p}"
    except PermissionError as e:
        return str(e)

    # 依序嘗試常見編碼
    content = None
    for enc in ("utf-8-sig", "utf-8", "big5", "cp950"):
        try:
            content = p.read_text(encoding=enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    if content is None:
        return f"無法解碼 CSV 檔案（嘗試過 utf-8、big5、cp950）：{p}"

    try:
        # 自動偵測分隔符（逗號 vs 分號 vs Tab）
        dialect = csv.Sniffer().sniff(content[:4096], delimiters=",;\t")
        reader  = csv.DictReader(content.splitlines(), dialect=dialect)
    except csv.Error:
        reader = csv.DictReader(content.splitlines())

    rows = list(reader)
    if not rows:
        return f"CSV 檔案是空的：{p}"

    headers = list(rows[0].keys())
    total   = len(rows)
    preview = rows[:max_rows]

    # 計算每欄最大寬度（用於對齊）
    col_w = {h: max(len(h), max(len(str(r.get(h, ""))) for r in preview))
             for h in headers}
    # 限制單欄最大寬度 30，避免過長
    col_w = {h: min(w, 30) for h, w in col_w.items()}

    def fmt_row(row: dict) -> str:
        return "  ".join(str(row.get(h, ""))[:col_w[h]].ljust(col_w[h]) for h in headers)

    header_line = "  ".join(h.ljust(col_w[h]) for h in headers)
    sep_line    = "  ".join("-" * col_w[h] for h in headers)
    data_lines  = [fmt_row(r) for r in preview]

    lines = [
        f"【{p.name}】共 {total} 筆，{len(headers)} 個欄位",
        f"欄位：{', '.join(headers)}",
        "",
        header_line,
        sep_line,
        *data_lines,
    ]
    if total > max_rows:
        lines.append(f"...（僅顯示前 {max_rows} 筆，剩餘 {total - max_rows} 筆）")

    return "\n".join(lines)


def move_file(src: str, dst: str) -> str:
    # 將檔案或目錄移動到新路徑（也可用來重新命名）
    # 來源與目標都必須在 WORKSPACE 範圍內
    # 若目標路徑已存在同名檔案，會直接覆蓋
    import shutil
    try:
        s = _safe_path(src)
        d = _safe_path(dst)
        if not s.exists():
            return f"來源不存在：{s}"
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(s), str(d))
        return f"已移動：{s}  →  {d}"
    except PermissionError as e:
        return str(e)
    except Exception as e:
        return f"移動失敗：{e}"


# ── 工具定義（送給 Ollama 的 JSON Schema）──────────
DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "列出指定資料夾內的檔案與子目錄（只允許 F:\\python_project\\ai_agent 範圍內）",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "要列出的資料夾路徑，留空則列根目錄"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "讀取指定路徑的文字檔案內容（只允許 F:\\python_project\\ai_agent 範圍內）",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "檔案的完整路徑"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "建立或覆寫指定路徑的文字檔案（只允許 F:\\python_project\\ai_agent 範圍內）",
            "parameters": {
                "type": "object",
                "properties": {
                    "path":    {"type": "string", "description": "檔案的完整路徑"},
                    "content": {"type": "string", "description": "要寫入的文字內容"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "append_file",
            "description": "在現有檔案末尾附加文字，檔案不存在則自動建立（只允許 F:\\python_project\\ai_agent 範圍內）",
            "parameters": {
                "type": "object",
                "properties": {
                    "path":    {"type": "string", "description": "檔案的完整路徑"},
                    "content": {"type": "string", "description": "要附加的文字內容"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "永久刪除指定檔案（不可復原），只能刪除單一檔案，不能刪除目錄（只允許 F:\\python_project\\ai_agent 範圍內）",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "要刪除的檔案完整路徑"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_csv",
            "description": (
                "讀取 CSV 檔案並回傳結構化摘要，包含欄位名稱、資料筆數與前 N 行預覽。"
                "自動偵測分隔符與編碼（UTF-8、Big5、CP950），適合讀取券商對帳單、財務報表等。"
                "只允許 F:\\python_project\\ai_agent 範圍內的路徑"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "CSV 檔案的完整路徑",
                    },
                    "max_rows": {
                        "type": "integer",
                        "description": "最多顯示幾行資料，預設 50",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move_file",
            "description": "移動檔案或目錄到新路徑，也可用來重新命名。來源與目標都必須在 F:\\python_project\\ai_agent 範圍內",
            "parameters": {
                "type": "object",
                "properties": {
                    "src": {"type": "string", "description": "來源路徑（檔案或目錄）"},
                    "dst": {"type": "string", "description": "目標路徑"},
                },
                "required": ["src", "dst"],
            },
        },
    },
]

# ── 工具實作對照表 ─────────────────────────────────
IMPLEMENTATIONS = {
    "list_files":  list_files,
    "read_file":   read_file,
    "write_file":  write_file,
    "append_file": append_file,
    "read_csv":    read_csv,
    "delete_file": delete_file,
    "move_file":   move_file,
}
