import requests

# ── 資料來源 ──────────────────────────────────────
# 台灣上市股票 → 台灣證交所 OpenAPI（官方、免費、無需 Key）
# 台灣上櫃股票 → 台灣證交所 OpenAPI（同上，部分端點涵蓋上櫃）
# 美股 / 其他  → Yahoo Finance 非官方 API（即時但非官方）
TWSE_DAY_ALL  = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TWSE_PE_ALL   = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
TWSE_INDEX    = "https://openapi.twse.com.tw/v1/exchangeReport/MI_INDEX"
YF_URL        = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
YF_HEADERS    = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

# TWSE 回應的日期格式為民國年，如 "1151014" = 民國115年10月14日 = 2026-10-14
def _roc_to_ad(roc_str: str) -> str:
    try:
        year = int(roc_str[:3]) + 1911
        return f"{year}-{roc_str[3:5]}-{roc_str[5:7]}"
    except Exception:
        return roc_str


def _is_tw_stock(symbol: str) -> bool:
    # 純數字視為台灣股票代碼（上市 4 碼、上櫃 4-5 碼）
    return symbol.replace(".", "").isdigit()


def _fetch_twse_all() -> tuple[dict, dict]:
    # 一次性下載全部上市股票的日成交資料與本益比資料
    # 回傳兩個以代碼為 key 的查詢字典
    try:
        r_day = requests.get(TWSE_DAY_ALL, timeout=15)
        r_day.raise_for_status()
        day_map = {row["Code"]: row for row in r_day.json()}
    except Exception:
        day_map = {}
    try:
        r_pe = requests.get(TWSE_PE_ALL, timeout=15)
        r_pe.raise_for_status()
        pe_map = {row["Code"]: row for row in r_pe.json()}
    except Exception:
        pe_map = {}
    return day_map, pe_map


def get_stock_price(symbol: str) -> str:
    # 查詢單一股票報價
    # 台股：台灣證交所官方 API（中文名稱、日收盤資料）
    # 美股：Yahoo Finance（即時，非官方）
    s = symbol.strip().upper()

    if _is_tw_stock(s):
        return _get_tw_stock(s)
    else:
        return _get_yf_stock(s)


def _get_tw_stock(code: str) -> str:
    # 查詢台灣上市股票（走 TWSE OpenAPI）
    day_map, pe_map = _fetch_twse_all()

    row = day_map.get(code)
    if not row:
        return (f"找不到上市股票代碼：{code}\n"
                f"（上市股票才支援官方 API，上櫃股票請加 .TWO 後用 Yahoo Finance 查詢，如 6547.TWO）")

    name   = row["Name"]
    date   = _roc_to_ad(row["Date"])
    close  = float(row["ClosingPrice"])
    open_p = float(row["OpeningPrice"])
    high   = float(row["HighestPrice"])
    low    = float(row["LowestPrice"])
    vol_raw = row.get("TradeVolume", "").strip()
    vol    = int(vol_raw) // 1000 if vol_raw.isdigit() else 0  # 單位：股 → 張（1張=1000股）
    # TWSE 的 Change 欄位帶正負號（漲為正，跌為負，平盤為 0）
    change_str = row["Change"].strip()
    change = float(change_str) if change_str else 0.0
    arrow = "▲" if change > 0 else ("▼" if change < 0 else "－")

    lines = [
        f"【{name}】{code}  （台灣證交所官方資料）",
        f"日期：{date}",
        f"收盤價：{close:.2f} TWD",
        f"漲跌：{arrow} {abs(change):.2f}",
        f"今日：開 {open_p:.2f} ／高 {high:.2f} ／低 {low:.2f}",
        f"成交量：{vol:,} 張",
    ]

    # 附加本益比、殖利率、股價淨值比（若有）
    pe = pe_map.get(code)
    if pe:
        pe_val = pe.get("PEratio", "")
        dy_val = pe.get("DividendYield", "")
        pb_val = pe.get("PBratio", "")
        extras = []
        if pe_val: extras.append(f"本益比 {pe_val}")
        if dy_val: extras.append(f"殖利率 {dy_val}%")
        if pb_val: extras.append(f"股價淨值比 {pb_val}")
        if extras:
            lines.append("估值：" + "　".join(extras))

    lines.append("※ 資料為當日收盤後更新，非即時報價")
    return "\n".join(lines)


def _get_yf_stock(symbol: str) -> str:
    # 查詢美股或其他交易所（走 Yahoo Finance）
    # 若是上櫃股票可傳入 "6547.TWO"
    try:
        resp = requests.get(
            YF_URL.format(symbol=symbol),
            headers=YF_HEADERS,
            params={"interval": "1d", "range": "2d"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return f"股價查詢失敗（{symbol}）：{e}"

    try:
        result = data["chart"]["result"]
        if not result:
            return f"找不到股票代碼：{symbol}"
        meta     = result[0]["meta"]
        price    = meta.get("regularMarketPrice")
        prev     = meta.get("previousClose") or meta.get("chartPreviousClose")
        day_high = meta.get("regularMarketDayHigh")
        day_low  = meta.get("regularMarketDayLow")
        volume   = meta.get("regularMarketVolume")
        currency = meta.get("currency", "")
        name     = meta.get("longName") or meta.get("shortName") or symbol
        exchange = meta.get("exchangeName", "")

        if price is None or prev is None:
            return f"查到了 {symbol} 但價格資料不完整（可能非交易時間）"

        change     = price - prev
        change_pct = (change / prev) * 100
        arrow      = "▲" if change >= 0 else "▼"

        vol_str = "N/A"
        if volume:
            vol_str = f"{volume / 1_000_000:.2f}M" if volume >= 1_000_000 else f"{volume:,}"

        lines = [
            f"【{name}】{symbol}  ({exchange})",
            f"現價：{price:,.2f} {currency}",
            f"漲跌：{arrow} {abs(change):,.2f}  ({change_pct:+.2f}%)",
            f"今日：最高 {day_high:,.2f} ／最低 {day_low:,.2f}" if day_high and day_low else "",
            f"昨收：{prev:,.2f}",
            f"成交量：{vol_str}",
        ]
        return "\n".join(l for l in lines if l)

    except (KeyError, IndexError, TypeError) as e:
        return f"股價資料解析失敗（{symbol}）：{e}"


def get_market_index() -> str:
    # 查詢台灣大盤指數（發行量加權股價指數等主要指數）
    try:
        resp = requests.get(TWSE_INDEX, timeout=10)
        resp.raise_for_status()
        rows = resp.json()
    except Exception as e:
        return f"大盤指數查詢失敗：{e}"

    # 只取最重要的幾個指數
    TARGET = {"發行量加權股價指數", "未含金融保險股指數", "未含電子股指數", "臺灣50指數"}
    lines = []
    date_str = ""
    for row in rows:
        name = row.get("指數", "")
        if name not in TARGET:
            continue
        if not date_str and row.get("日期"):
            date_str = _roc_to_ad(row["日期"])
        close  = row.get("收盤指數", "")
        sign   = row.get("漲跌", "")
        pts    = row.get("漲跌點數", "")
        pct    = row.get("漲跌百分比", "")
        arrow  = "▲" if sign == "+" else ("▼" if sign == "-" else "－")
        lines.append(f"{name}：{close}  {arrow} {pts}（{pct}%）")

    if not lines:
        return "無法取得大盤指數資料"

    return f"【台灣大盤指數】{date_str}\n" + "\n".join(lines) + "\n※ 資料為當日收盤後更新"


def get_multiple_stocks(symbols: str) -> str:
    # 一次查詢多支股票，逗號分隔，例如："2330,2454,AAPL"
    tickers = [s.strip() for s in symbols.split(",") if s.strip()]
    if not tickers:
        return "請提供至少一個股票代碼"
    if len(tickers) > 10:
        return "單次最多查詢 10 支股票"

    # 台股批次查詢：只下載一次完整資料再過濾，避免重複呼叫
    tw_codes = [t for t in tickers if _is_tw_stock(t)]
    us_codes = [t for t in tickers if not _is_tw_stock(t)]

    results = []

    if tw_codes:
        day_map, pe_map = _fetch_twse_all()
        for code in tw_codes:
            row = day_map.get(code)
            if not row:
                results.append(f"【{code}】找不到上市股票資料")
                continue
            name       = row["Name"]
            date       = _roc_to_ad(row["Date"])
            close      = float(row["ClosingPrice"])
            change_str = row.get("Change", "").strip()
            change     = float(change_str) if change_str else 0.0
            arrow      = "▲" if change > 0 else ("▼" if change < 0 else "－")
            results.append(f"【{name}】{code}  {close:.2f} TWD  {arrow} {abs(change):.2f}  ({date})")

    for sym in us_codes:
        results.append(_get_yf_stock(sym))

    return "\n\n─────\n\n".join(results)


# ── 工具定義（送給 Ollama 的 JSON Schema）──────────
DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_stock_price",
            "description": "查詢單一股票的報價與基本資訊。台灣上市股票走官方證交所 API（輸入純數字代碼如 2330），台灣上櫃請加 .TWO（如 6547.TWO），美股輸入英文代碼（如 AAPL）",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "股票代碼，例如：2330（台積電）、0050（台灣50）、AAPL（蘋果）、6547.TWO（上櫃股）",
                    },
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_market_index",
            "description": "查詢台灣大盤指數，包含發行量加權股價指數、未含金融股指數、未含電子股指數等",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_multiple_stocks",
            "description": "一次查詢多支股票的報價摘要，代碼以逗號分隔，最多 10 支。台股與美股可混查",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbols": {
                        "type": "string",
                        "description": "股票代碼，逗號分隔，例如：2330,2454,AAPL,TSLA",
                    },
                },
                "required": ["symbols"],
            },
        },
    },
]

# ── 工具實作對照表 ─────────────────────────────────
IMPLEMENTATIONS = {
    "get_stock_price":     get_stock_price,
    "get_market_index":    get_market_index,
    "get_multiple_stocks": get_multiple_stocks,
}
