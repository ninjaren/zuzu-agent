from tools.file_ops import _safe_path


def read_pdf(path: str) -> str:
    # 讀取 PDF 全文，每頁用分隔線隔開方便閱讀
    # 注意：超長 PDF 可能超過模型的 context window 上限，
    # 建議改用 read_pdf_page 分批讀取
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(_safe_path(path)))
        pages = []
        for i, page in enumerate(reader.pages):
            text = (page.extract_text() or "").strip()
            if text:
                pages.append(f"── 第 {i+1} 頁 ──\n{text}")
        if not pages:
            return "PDF 無可提取的文字（可能是掃描圖片版，需要 OCR）"
        return f"共 {len(reader.pages)} 頁\n\n" + "\n\n".join(pages)
    except PermissionError as e:
        return str(e)
    except Exception as e:
        return f"PDF 讀取失敗：{e}"


def read_pdf_page(path: str, start_page: int, end_page: int) -> str:
    # 讀取指定頁數範圍的文字（頁碼從 1 開始，含頭含尾）
    # 適合分批處理長篇電子書，避免一次送太多內容給模型
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(_safe_path(path)))
        total = len(reader.pages)
        start = max(1, start_page)
        end   = min(end_page, total)
        if start > total:
            return f"超出範圍：此 PDF 共 {total} 頁"
        pages = []
        for i in range(start - 1, end):
            text = (reader.pages[i].extract_text() or "").strip()
            if text:
                pages.append(f"── 第 {i+1} 頁 ──\n{text}")
        return f"第 {start}-{end} 頁（共 {total} 頁）\n\n" + "\n\n".join(pages) if pages else "此範圍無可提取文字"
    except PermissionError as e:
        return str(e)
    except Exception as e:
        return f"PDF 讀取失敗：{e}"


def split_pdf(path: str, start_page: int, end_page: int, output_path: str) -> str:
    # 從來源 PDF 切出指定頁數範圍，另存為新的 PDF 檔案
    # 輸出路徑同樣受 WORKSPACE 路徑安全限制
    try:
        from pypdf import PdfReader, PdfWriter
        src = _safe_path(path)
        dst = _safe_path(output_path)
        reader = PdfReader(str(src))
        total  = len(reader.pages)
        start  = max(1, start_page)
        end    = min(end_page, total)
        if start > total:
            return f"超出範圍：此 PDF 共 {total} 頁"
        writer = PdfWriter()
        for i in range(start - 1, end):
            writer.add_page(reader.pages[i])
        dst.parent.mkdir(parents=True, exist_ok=True)
        with open(dst, "wb") as f:
            writer.write(f)
        return f"已切出第 {start}-{end} 頁（共 {end - start + 1} 頁），存至：{dst}"
    except PermissionError as e:
        return str(e)
    except Exception as e:
        return f"PDF 切割失敗：{e}"


# ── 工具定義（送給 Ollama 的 JSON Schema）──────────
DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "read_pdf",
            "description": "讀取 PDF 檔案的全部文字內容。超長文件建議改用 read_pdf_page 分批讀取",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "PDF 檔案的完整路徑"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_pdf_page",
            "description": "讀取 PDF 指定頁數範圍的文字，適合分批處理長篇電子書（頁碼從 1 開始）",
            "parameters": {
                "type": "object",
                "properties": {
                    "path":       {"type": "string",  "description": "PDF 檔案的完整路徑"},
                    "start_page": {"type": "integer", "description": "起始頁碼（含，從 1 開始）"},
                    "end_page":   {"type": "integer", "description": "結束頁碼（含）"},
                },
                "required": ["path", "start_page", "end_page"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "split_pdf",
            "description": "從 PDF 切出指定頁數範圍，儲存成新的 PDF 檔案",
            "parameters": {
                "type": "object",
                "properties": {
                    "path":        {"type": "string",  "description": "來源 PDF 的完整路徑"},
                    "start_page":  {"type": "integer", "description": "起始頁碼（含，從 1 開始）"},
                    "end_page":    {"type": "integer", "description": "結束頁碼（含）"},
                    "output_path": {"type": "string",  "description": "輸出 PDF 的完整路徑"},
                },
                "required": ["path", "start_page", "end_page", "output_path"],
            },
        },
    },
]

# ── 工具實作對照表 ─────────────────────────────────
IMPLEMENTATIONS = {
    "read_pdf":      read_pdf,
    "read_pdf_page": read_pdf_page,
    "split_pdf":     split_pdf,
}
