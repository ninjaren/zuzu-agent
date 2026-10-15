import requests
from datetime import datetime
from pathlib import Path

# Agg 後端：不需要顯示視窗，適合伺服器環境
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker

# 圖表存放目錄（自動建立）
CHART_DIR = Path(r"F:\python_project\ai_agent\data\charts")

YF_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
YF_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

VALID_PERIODS   = {"1mo", "3mo", "6mo", "1y", "2y", "5y"}
VALID_INTERVALS = {"1d", "1wk"}


def _tw_symbol(symbol: str) -> str:
    # 純數字台股代碼自動補 .TW（若已有後綴則不改）
    s = symbol.strip().upper()
    if s.replace(".", "").isdigit() and "." not in s:
        return s + ".TW"
    return s


def _moving_avg(data: list[float | None], n: int) -> list[float | None]:
    # 計算 N 日均線，前 n-1 天填 None
    result: list[float | None] = [None] * (n - 1)
    for i in range(n - 1, len(data)):
        window = [v for v in data[i - n + 1: i + 1] if v is not None]
        result.append(sum(window) / len(window) if len(window) == n else None)
    return result


def plot_stock_chart(symbol: str, period: str = "3mo") -> str:
    # 繪製股票價格走勢圖（折線 + MA5 + MA20 + 成交量），存為 PNG
    # 回傳圖片絕對路徑，讓 analyze_image 或使用者直接查看
    sym = _tw_symbol(symbol)
    period = period if period in VALID_PERIODS else "3mo"

    # ── 取得歷史資料 ──────────────────────────────────
    try:
        resp = requests.get(
            YF_URL.format(symbol=sym),
            headers=YF_HEADERS,
            params={"interval": "1d", "range": period},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return f"圖表資料取得失敗（{sym}）：{e}"

    try:
        result = data["chart"]["result"]
        if not result:
            return f"找不到股票代碼：{sym}"

        meta       = result[0]["meta"]
        timestamps = result[0].get("timestamp", [])
        quote      = result[0]["indicators"]["quote"][0]

        closes  = quote.get("close",  [])
        opens   = quote.get("open",   [])
        volumes = quote.get("volume", [])

        if not timestamps or not closes:
            return f"無法取得 {sym} 的歷史資料（可能是非交易日或代碼錯誤）"

        # 過濾 None（可能有節假日空洞）
        dates = [datetime.fromtimestamp(ts) for ts in timestamps]
        valid = [(d, c, o, v)
                 for d, c, o, v in zip(dates, closes, opens, volumes)
                 if c is not None]
        if not valid:
            return f"{sym} 的歷史資料全為空（非交易時段）"

        dates, closes, opens, volumes = zip(*valid)
        dates   = list(dates)
        closes  = list(closes)
        opens   = list(opens)
        volumes = [v or 0 for v in volumes]

        name     = meta.get("longName") or meta.get("shortName") or sym
        currency = meta.get("currency", "")

    except (KeyError, IndexError, TypeError) as e:
        return f"歷史資料解析失敗（{sym}）：{e}"

    # ── 計算均線 ──────────────────────────────────────
    ma5  = _moving_avg(closes, 5)
    ma20 = _moving_avg(closes, 20)

    # ── 繪圖 ─────────────────────────────────────────
    fig, (ax1, ax2) = plt.subplots(
        2, 1,
        figsize=(12, 7),
        gridspec_kw={"height_ratios": [3, 1]},
        sharex=True,
    )
    fig.patch.set_facecolor("#0d1117")
    for ax in (ax1, ax2):
        ax.set_facecolor("#161b22")
        ax.tick_params(colors="#8b949e", labelsize=9)
        for spine in ax.spines.values():
            spine.set_edgecolor("#30363d")

    # ── 上方：收盤價折線 + MA ─────────────────────────
    ax1.plot(dates, closes, color="#58a6ff", linewidth=1.2, label="收盤價", zorder=3)

    # MA5 / MA20
    ma5_dates  = [d for d, v in zip(dates, ma5)  if v is not None]
    ma5_vals   = [v for v in ma5  if v is not None]
    ma20_dates = [d for d, v in zip(dates, ma20) if v is not None]
    ma20_vals  = [v for v in ma20 if v is not None]
    if ma5_dates:
        ax1.plot(ma5_dates,  ma5_vals,  color="#f0883e", linewidth=0.9, label="MA5",  alpha=0.8)
    if ma20_dates:
        ax1.plot(ma20_dates, ma20_vals, color="#bc8cff", linewidth=0.9, label="MA20", alpha=0.8)

    ax1.set_ylabel(f"價格 ({currency})", color="#8b949e", fontsize=9)
    ax1.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.2f"))
    ax1.legend(loc="upper left", fontsize=8, facecolor="#161b22",
               edgecolor="#30363d", labelcolor="#c9d1d9")
    ax1.grid(color="#21262d", linewidth=0.5, linestyle="--", alpha=0.7)

    title_str = f"{name} ({sym})  ·  {period} 走勢"
    ax1.set_title(title_str, color="#e6edf3", fontsize=11, pad=8, fontweight="bold")

    # ── 下方：成交量長條 ─────────────────────────────
    colors = ["#3fb950" if c >= o else "#f85149"
              for c, o in zip(closes, opens)]
    ax2.bar(dates, volumes, color=colors, width=0.8, alpha=0.85)

    # 自動縮放單位（百萬 / 千）
    max_vol = max(volumes) if volumes else 1
    if max_vol >= 1_000_000:
        ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v/1e6:.1f}M"))
    elif max_vol >= 1_000:
        ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v/1e3:.0f}K"))
    ax2.set_ylabel("成交量", color="#8b949e", fontsize=9)
    ax2.grid(color="#21262d", linewidth=0.5, linestyle="--", alpha=0.7, axis="y")

    # ── X 軸日期格式 ──────────────────────────────────
    if len(dates) <= 35:
        ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
        ax2.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0))
    elif len(dates) <= 130:
        ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
        ax2.xaxis.set_major_locator(mdates.MonthLocator())
    else:
        ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y/%m"))
        ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=2))

    plt.xticks(rotation=30, ha="right", color="#8b949e", fontsize=8)

    plt.tight_layout(pad=1.5)

    # ── 存檔 ─────────────────────────────────────────
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    date_tag  = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_sym  = sym.replace(".", "_")
    out_path  = CHART_DIR / f"{safe_sym}_{period}_{date_tag}.png"
    fig.savefig(out_path, dpi=130, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)

    return str(out_path)


# ── 工具定義（送給 Ollama 的 JSON Schema）──────────
DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "plot_stock_chart",
            "description": (
                "繪製股票價格走勢圖並存為 PNG 圖片，包含收盤價折線、MA5、MA20 均線與成交量柱狀圖。"
                "適合使用者說「畫圖」、「看走勢」、「技術圖」時使用。"
                "回傳圖片的本機路徑，可搭配 analyze_image 進行後續分析。"
                "台股輸入純數字代碼（如 2330），會自動加上 .TW；美股輸入英文代碼（如 AAPL）。"
                "period 可選：1mo / 3mo / 6mo / 1y / 2y / 5y，預設 3mo"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "股票代碼，例如：2330（台積電）、0050、AAPL、TSLA",
                    },
                    "period": {
                        "type": "string",
                        "description": "查詢區間：1mo / 3mo / 6mo / 1y / 2y / 5y，預設 3mo",
                    },
                },
                "required": ["symbol"],
            },
        },
    },
]

# ── 工具實作對照表 ─────────────────────────────────
IMPLEMENTATIONS = {
    "plot_stock_chart": plot_stock_chart,
}
