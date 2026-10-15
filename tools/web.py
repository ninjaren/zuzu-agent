import re
import time
import threading
import xml.etree.ElementTree as ET
from collections import defaultdict
from urllib.parse import urlparse, urljoin
import requests

# ── 速率限制設定 ──────────────────────────────────
# 同一個網域在一次對話中最多 browse 幾次，防止被目標網站封鎖
MAX_BROWSE_PER_DOMAIN = 5
# 每次 browse_url 之間強制等待秒數，模擬人類瀏覽節奏
BROWSE_DELAY_SECONDS = 1

# 不允許爬取的社群平台（需要登入或有嚴格反爬蟲）
DOMAIN_BLACKLIST = {
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "linkedin.com",
}

# ── 執行緒安全的計數器 ────────────────────────────
# 每次新對話由 agent_runner 呼叫 reset_browse_counts() 清零
_domain_counts: dict = defaultdict(int)
_lock = threading.Lock()          # 保護 _domain_counts 與 _last_browse_time
_last_browse_time: float = 0.0    # 上一次 browse_url 的時間戳


def reset_browse_counts():
    # 每次新對話開始時呼叫，重設各網域的訪問計數器
    with _lock:
        _domain_counts.clear()


def _extract_domain(url: str) -> str:
    # 從完整 URL 擷取網域，移除 www. 前綴方便做黑名單比對
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return url


def search_web(query: str) -> str:
    # 用 DuckDuckGo 搜尋，回傳最多 5 筆結果（標題、摘要、網址）
    # 不需要 API Key，適合本機輕量使用
    from ddgs import DDGS
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=5))
    if not results:
        return "沒有找到相關結果，請換個關鍵字"
    return "\n\n".join(
        f"[{i+1}] 標題: {r['title']}\n    摘要: {r['body']}\n    網址: {r['href']}"
        for i, r in enumerate(results)
    )


# JS 框架常見的標記字串，用於輔助判斷是否為動態渲染頁面
_JS_MARKERS = [
    "__NEXT_DATA__", "__NUXT__", "window.__INITIAL_STATE__",
    "data-reactroot", "ng-version", "data-vue", "__REACT_",
    "ReactDOM.render", "window.__data", "window.App",
]


def _is_js_rendered(html: str, text: str) -> bool:
    # 判斷此頁面是否為 JS 動態渲染的空殼（靜態 GET 拿不到實際內容）
    # 邏輯：HTML 夠大（不是空頁）但提取到的文字極少，才算是空殼
    # 若文字已足夠（≥300 字），即使有 JS 框架也代表 SSR 有給出內容，不誤判
    text_stripped = text.strip()
    if len(html) < 2000:
        return False  # 頁面本身就很小，不算 JS 空殼
    if len(text_stripped) >= 300:
        return False  # 文字夠多，內容可用
    # 文字極少時：有 JS 框架標記確認是 SPA，或文字少到幾乎沒有
    return any(m in html for m in _JS_MARKERS) or len(text_stripped) < 100


def browse_url(url: str) -> str:
    # 抓取網頁並移除 HTML 標籤，回傳純文字（最多 5000 字）
    # 內建速率限制、黑名單過濾、JS 動態渲染空殼偵測
    global _last_browse_time

    domain = _extract_domain(url)

    # 黑名單檢查（完整網域或子網域）
    if any(domain == b or domain.endswith("." + b) for b in DOMAIN_BLACKLIST):
        return f"拒絕訪問：{domain} 在黑名單中"

    # 同網域訪問次數上限，防止短時間大量請求被封鎖
    with _lock:
        if _domain_counts[domain] >= MAX_BROWSE_PER_DOMAIN:
            return f"拒絕訪問：{domain} 本次對話已訪問 {MAX_BROWSE_PER_DOMAIN} 次，已達上限"
        _domain_counts[domain] += 1

    # 強制間隔，避免連打同一伺服器
    with _lock:
        elapsed = time.time() - _last_browse_time
        if elapsed < BROWSE_DELAY_SECONDS:
            time.sleep(BROWSE_DELAY_SECONDS - elapsed)
        _last_browse_time = time.time()

    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        html = resp.text

        # 移除 script、style 標籤，再去掉所有 HTML 標記，合併多餘空白
        text = re.sub(r"<script[^>]*>[\s\S]*?</script>", "", html)
        text = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", text)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()

        # JS 動態渲染空殼偵測：直接告訴模型要換策略，不依賴 system prompt
        if _is_js_rendered(html, text):
            return (f"[JS渲染頁面] {url} 的內容需要 JavaScript 才能載入，"
                    f"直接讀取無法取得實際資料。"
                    f"請改用 search_web 搜尋相關新聞或文章。")

        return text[:5000] + ("…（內容截斷）" if len(text) > 5000 else "")
    except Exception as e:
        return f"無法讀取網頁：{e}"


def fetch_rss(url: str, max_items: int = 10) -> str:
    # 解析 RSS 2.0 或 Atom feed，回傳最新幾筆文章的標題、日期、摘要、網址
    # 比 browse_url 更快、更乾淨，且不觸發反爬蟲機制
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)

        items = []

        # 嘗試解析 RSS 2.0 格式：<rss><channel><item>
        for item in root.findall(".//item")[:max_items]:
            title = item.findtext("title", "").strip()
            link  = item.findtext("link",  "").strip()
            desc  = re.sub(r"<[^>]+>", "", item.findtext("description", "")).strip()
            pub   = item.findtext("pubDate", "").strip()
            items.append((title, link, desc[:200], pub))

        # 若 RSS 沒有結果，嘗試解析 Atom 格式：<feed><entry>
        if not items:
            atom = {"a": "http://www.w3.org/2005/Atom"}
            for entry in root.findall(".//a:entry", atom)[:max_items]:
                title    = entry.findtext("a:title",   "", atom).strip()
                link_el  = entry.find("a:link", atom)
                link     = link_el.get("href", "") if link_el is not None else ""
                summary  = re.sub(r"<[^>]+>", "", entry.findtext("a:summary", "", atom)).strip()
                pub      = entry.findtext("a:published", "", atom).strip()
                items.append((title, link, summary[:200], pub))

        if not items:
            return "無法解析此 RSS/Atom feed，請確認網址正確"

        return "\n\n".join(
            f"[{i+1}] 標題: {t}\n    日期: {p}\n    摘要: {d}\n    網址: {l}"
            for i, (t, l, d, p) in enumerate(items)
        )
    except Exception as e:
        return f"RSS 讀取失敗：{e}"


def extract_links(url: str, max_links: int = 20) -> str:
    # 從網頁抓出所有超連結（<a href>），供模型決定下一步要深入哪幾篇
    # 適合在拿到新聞列表頁後，先看有哪些文章再選擇性 browse
    domain = _extract_domain(url)
    if any(domain == b or domain.endswith("." + b) for b in DOMAIN_BLACKLIST):
        return f"拒絕訪問：{domain} 在黑名單中"

    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()

        # 用正則擷取 href 與連結文字，過濾錨點（#）與相對路徑
        raw = re.findall(r'<a[^>]+href=["\']([^"\'#][^"\']*)["\'][^>]*>(.*?)</a>',
                         resp.text, re.IGNORECASE | re.DOTALL)

        seen, links = set(), []
        for href, text in raw:
            href = urljoin(url, href.strip())   # 補全相對路徑
            if not href.startswith("http") or href in seen:
                continue
            seen.add(href)
            text = re.sub(r"<[^>]+>", "", text).strip()[:50] or "（無文字）"
            links.append((text, href))
            if len(links) >= max_links:
                break

        if not links:
            return "此頁面未找到任何連結"

        return f"找到 {len(links)} 個連結：\n\n" + "\n".join(
            f"[{i+1}] {t}\n    → {u}" for i, (t, u) in enumerate(links)
        )
    except Exception as e:
        return f"連結提取失敗：{e}"


# ── 工具定義（送給 Ollama 的 JSON Schema）──────────
DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "用關鍵字搜尋網路，回傳多筆結果的標題、摘要與網址。若摘要不夠詳細，可用 browse_url 讀取網頁完整內容",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜尋關鍵字，越精確越好"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browse_url",
            "description": "讀取指定網址的完整網頁內容，適合在搜尋後想深入閱讀某篇文章時使用。每個網域每次對話最多讀取 5 次",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "要讀取的網頁網址"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_rss",
            "description": "讀取 RSS 或 Atom feed，回傳最新文章的標題、日期、摘要與網址，比 browse_url 更快更乾淨，適合新聞網站、部落格、論壇",
            "parameters": {
                "type": "object",
                "properties": {
                    "url":       {"type": "string",  "description": "RSS 或 Atom feed 的網址"},
                    "max_items": {"type": "integer", "description": "最多回傳幾筆，預設 10"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "extract_links",
            "description": "從網頁中提取所有超連結，供進一步決定要深入閱讀哪幾篇，適合在拿到列表頁後選出值得 browse 的文章",
            "parameters": {
                "type": "object",
                "properties": {
                    "url":       {"type": "string",  "description": "要提取連結的網頁網址"},
                    "max_links": {"type": "integer", "description": "最多回傳幾條連結，預設 20"},
                },
                "required": ["url"],
            },
        },
    },
]

# ── 工具實作對照表 ─────────────────────────────────
IMPLEMENTATIONS = {
    "search_web":    search_web,
    "browse_url":    browse_url,
    "fetch_rss":     fetch_rss,
    "extract_links": extract_links,
}
