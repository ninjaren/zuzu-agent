import json
import re
import requests
from datetime import datetime
from pathlib import Path

try:
    from config import OLLAMA_URL, MODEL as DEFAULT_MODEL
except ImportError:
    # 在套件外直接執行時的 fallback（例如單元測試）
    OLLAMA_URL   = "http://localhost:11434/api/chat"
    DEFAULT_MODEL = "qwen3:8b"

# 報告輸出目錄與重複出現紀錄檔
REPORT_DIR = Path(r"F:\python_project\ai_agent\data\weekly_github")
SEEN_FILE  = REPORT_DIR / "seen.json"

TRENDING_URL = "https://github.com/trending?since=weekly"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ── 工具函式 ──────────────────────────────────────

def _week_id() -> str:
    # 回傳 ISO 週次字串，例如 2026-W42
    y, w, _ = datetime.now().isocalendar()
    return f"{y}-W{w:02d}"


def _load_seen() -> dict:
    # 讀取已出現過的 repo 紀錄（first_week + 每次出現的週次列表）
    if SEEN_FILE.exists():
        try:
            return json.loads(SEEN_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_seen(seen: dict):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(
        json.dumps(seen, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _parse_trending(html: str) -> list[dict]:
    # 解析 GitHub Trending 頁面 HTML，回傳最多 25 筆 repo 資料
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    soup  = BeautifulSoup(html, "html.parser")
    repos = []

    for article in soup.select("article.Box-row"):
        try:
            # Repo 完整路徑，例如 "microsoft/typescript"
            link = article.select_one("h2 a, h1 a")
            if not link:
                continue
            repo_path = link.get("href", "").strip("/")
            if not repo_path or "/" not in repo_path:
                continue

            # 描述
            desc_el = article.select_one("p")
            description = desc_el.get_text(strip=True) if desc_el else ""

            # 程式語言
            lang_el = article.select_one("[itemprop='programmingLanguage']")
            language = lang_el.get_text(strip=True) if lang_el else ""

            # 本週新增星星數
            week_stars = 0
            for el in article.find_all(string=re.compile(r"stars?\s+this\s+week", re.I)):
                m = re.search(r"([\d,]+)\s+stars?\s+this\s+week", el, re.I)
                if m:
                    week_stars = int(m.group(1).replace(",", ""))
                    break

            # 總星星數
            total_stars = 0
            for a in article.select("a[href*='/stargazers']"):
                text = re.sub(r"[^\d]", "", a.get_text())
                if text.isdigit():
                    total_stars = int(text)
                    break

            repos.append({
                "repo":        repo_path,
                "description": description,
                "language":    language,
                "week_stars":  week_stars,
                "total_stars": total_stars,
                "url":         f"https://github.com/{repo_path}",
            })
        except Exception:
            continue

    return repos


def _translate_batch(descriptions: list[str], model: str = DEFAULT_MODEL) -> list[str]:
    # 批次翻譯描述成繁體中文（一次 API call，效率高於逐條翻譯）
    # 回傳與輸入等長的列表；失敗時回傳原文
    numbered = "\n".join(f"{i+1}. {d}" for i, d in enumerate(descriptions))
    prompt = (
        "請將以下英文描述逐條翻譯成繁體中文。\n"
        "格式：只輸出翻譯結果，每條一行，保留編號，不要加任何解釋。\n"
        "專案名稱（如 owner/repo 格式）一律不翻譯。\n\n"
        f"{numbered}"
    )
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={
                "model":    model,
                "messages": [{"role": "user", "content": prompt}],
                "stream":   False,
                "think":    False,
            },
            timeout=120,
        )
        resp.raise_for_status()
        raw = resp.json()["message"]["content"].strip()

        # 解析回傳的 "1. xxx\n2. xxx\n..." 格式
        result = []
        for line in raw.splitlines():
            m = re.match(r"^\d+\.\s*(.*)", line.strip())
            if m:
                result.append(m.group(1).strip())
        # 補齊長度（若模型少回傳幾條）
        while len(result) < len(descriptions):
            result.append(descriptions[len(result)])
        return result[:len(descriptions)]

    except Exception:
        return descriptions  # 翻譯失敗退回原文


def _update_seen(repos: list[dict], week: str) -> list[dict]:
    # 更新 seen.json，並在每筆 repo 加入 badge 欄位
    seen = _load_seen()
    for repo in repos:
        name = repo["repo"]
        if name not in seen:
            seen[name] = {"first_week": week, "weeks": [week]}
            repo["badge"] = "🆕 首次上榜"
        else:
            weeks_list = seen[name].get("weeks", [])
            if week not in weeks_list:
                weeks_list.append(week)
                seen[name]["weeks"] = weeks_list
            n = len(weeks_list)
            repo["badge"] = f"🔁 連續上榜 {n} 週" if n > 1 else "🆕 首次上榜"
    _save_seen(seen)
    return repos


# ── 對外 API ──────────────────────────────────────

def get_github_trending(count: int = 10) -> str:
    # 抓取 GitHub 本週熱門專案，回傳結構化文字給 agent
    # 描述為英文原文，agent 負責翻譯（不在工具內翻，避免雙重 LLM call）
    try:
        resp = requests.get(TRENDING_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        return f"GitHub Trending 取得失敗：{e}"

    repos = _parse_trending(resp.text)
    if not repos:
        return (
            "無法解析 GitHub Trending 頁面（請確認已安裝：pip install beautifulsoup4）"
        )

    week  = _week_id()
    repos = _update_seen(repos[:count], week)

    lines = [f"【GitHub 本週熱門專案】{week}（共 {len(repos)} 筆）\n"]
    for i, r in enumerate(repos, 1):
        lang   = f"語言：{r['language']}　" if r["language"] else ""
        stars  = f"⭐ 本週 +{r['week_stars']:,}" if r["week_stars"] else ""
        total  = f"（共 {r['total_stars']:,}）" if r["total_stars"] else ""
        lines += [
            f"{i}. {r['badge']}  {r['repo']}",
            f"   {lang}{stars} {total}",
            f"   {r['description']}" if r["description"] else "",
            f"   🔗 {r['url']}",
            "",
        ]
    lines.append("（描述為英文原文，請翻譯成繁體中文後輸出並存入週報 .md 檔）")
    return "\n".join(l for l in lines)


def generate_weekly_report(model: str = DEFAULT_MODEL) -> str:
    # 自動產生本週週報 .md 並寫入磁碟（供 app 啟動時背景呼叫）
    # 包含批次翻譯描述，不需要使用者手動觸發
    week      = _week_id()
    out_path  = REPORT_DIR / f"{week}.md"

    if out_path.exists():
        return f"本週報告已存在：{out_path}"

    try:
        resp = requests.get(TRENDING_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        return f"GitHub Trending 取得失敗：{e}"

    repos = _parse_trending(resp.text)
    if not repos:
        return "無法解析 GitHub Trending 頁面"

    repos = repos[:10]
    repos = _update_seen(repos, week)

    # 批次翻譯有描述的項目
    descs      = [r["description"] for r in repos]
    translated = _translate_batch(descs, model)

    # 組合 .md 內容
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines   = [
        f"# GitHub 本週熱門專案 — {week}",
        f"\n> 資料來源：[GitHub Trending]({TRENDING_URL})（週增星數排名）  ",
        f"> 產生時間：{now_str}  ",
        f"> 描述由 `{model}` 自動翻譯\n",
        "---\n",
    ]

    for i, (repo, zh_desc) in enumerate(zip(repos, translated), 1):
        lang  = f"**語言**：{repo['language']}　" if repo["language"] else ""
        stars = f"⭐ 本週 +{repo['week_stars']:,} stars" if repo["week_stars"] else ""
        total = f"（共 {repo['total_stars']:,}）" if repo["total_stars"] else ""

        lines += [
            f"## {i}. {repo['badge']}　`{repo['repo']}`",
            f"{lang}{stars} {total}\n",
            f"{zh_desc}\n",
            f"> 原文：{repo['description']}\n" if repo["description"] else "",
            f"🔗 {repo['url']}\n",
            "---\n",
        ]

    content = "\n".join(lines)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    return f"週報已寫入：{out_path}"


# ── 工具定義（送給 Ollama 的 JSON Schema）──────────
DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_github_trending",
            "description": (
                "抓取 GitHub 本週熱門專案（依週增星數排名），回傳前 N 名的"
                "專案名稱、描述（英文原文）、語言、本週星星數與是否重複上榜。"
                "收到結果後請將描述翻譯成繁體中文，並可使用 write_file 存成週報 .md 檔。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "count": {
                        "type": "integer",
                        "description": "要抓幾筆，預設 10，最多 25",
                    },
                },
            },
        },
    },
]

# ── 工具實作對照表 ─────────────────────────────────
IMPLEMENTATIONS = {
    "get_github_trending": get_github_trending,
}
