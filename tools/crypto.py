import requests

# ── 虛擬貨幣：CoinGecko 免費 API，不需 Key ────────
COINGECKO_PRICE  = "https://api.coingecko.com/api/v3/simple/price"
COINGECKO_SEARCH = "https://api.coingecko.com/api/v3/search"
CG_HEADERS = {"User-Agent": "curl/7.68.0", "Accept": "application/json"}

# ── 匯率：Open Exchange Rates 免費端點（無需 Key）──
ER_URL = "https://open.er-api.com/v6/latest/{base}"

# 常見幣種符號 → CoinGecko coin ID
_COIN_IDS: dict[str, str] = {
    "BTC":   "bitcoin",       "ETH":  "ethereum",      "SOL":  "solana",
    "BNB":   "binancecoin",   "XRP":  "ripple",         "ADA":  "cardano",
    "DOGE":  "dogecoin",      "AVAX": "avalanche-2",    "DOT":  "polkadot",
    "MATIC": "matic-network", "LINK": "chainlink",      "UNI":  "uniswap",
    "ATOM":  "cosmos",        "LTC":  "litecoin",       "BCH":  "bitcoin-cash",
    "FIL":   "filecoin",      "APT":  "aptos",          "OP":   "optimism",
    "ARB":   "arbitrum",      "SUI":  "sui",            "TRX":  "tron",
    "SHIB":  "shiba-inu",     "PEPE": "pepe",           "TON":  "the-open-network",
    "NEAR":  "near",          "ICP":  "internet-computer",
}


def _resolve_coin_id(symbol: str) -> str | None:
    # 先查靜態對照表，找不到再呼叫 CoinGecko search 端點
    s = symbol.upper()
    if s in _COIN_IDS:
        return _COIN_IDS[s]
    try:
        resp = requests.get(COINGECKO_SEARCH, params={"query": s},
                            headers=CG_HEADERS, timeout=10)
        resp.raise_for_status()
        for coin in resp.json().get("coins", []):
            if coin.get("symbol", "").upper() == s:
                return coin["id"]
    except Exception:
        pass
    return None


def get_crypto_price(symbol: str) -> str:
    # 查詢虛擬貨幣即時報價（美元＋台幣），含 24h 漲跌幅與市值
    sym = symbol.strip().upper()
    coin_id = _resolve_coin_id(sym)
    if not coin_id:
        return f"找不到虛擬貨幣代號：{sym}（請用英文縮寫，如 BTC、ETH、SOL）"

    try:
        resp = requests.get(
            COINGECKO_PRICE,
            headers=CG_HEADERS,
            params={
                "ids": coin_id,
                "vs_currencies": "usd,twd",
                "include_24hr_change": "true",
                "include_market_cap": "true",
                "include_24hr_vol":   "true",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json().get(coin_id, {})
    except Exception as e:
        return f"虛擬貨幣查詢失敗（{sym}）：{e}"

    if not data:
        return f"查不到 {sym} 的報價資料"

    usd        = data.get("usd")
    twd        = data.get("twd")
    change_24h = data.get("usd_24h_change")
    market_cap = data.get("usd_market_cap")
    vol_24h    = data.get("usd_24h_vol")

    lines = [f"【{sym}】（{coin_id}）"]

    if usd is not None:
        usd_str = f"${usd:,.6f}" if usd < 1 else f"${usd:,.2f}"
        twd_str = f"  /  NT${twd:,.2f}" if twd else ""
        lines.append(f"現價：{usd_str} USD{twd_str}")

    if change_24h is not None:
        arrow = "▲" if change_24h >= 0 else "▼"
        lines.append(f"24h 漲跌：{arrow} {abs(change_24h):.2f}%")

    if market_cap:
        lines.append(f"市值：${market_cap / 1e9:.2f}B USD")

    if vol_24h:
        lines.append(f"24h 成交量：${vol_24h / 1e6:.2f}M USD")

    return "\n".join(lines)


def get_multiple_cryptos(symbols: str) -> str:
    # 一次查詢多個虛擬貨幣，逗號分隔，最多 10 個
    tickers = [s.strip() for s in symbols.split(",") if s.strip()]
    if not tickers:
        return "請提供至少一個虛擬貨幣代號"
    if len(tickers) > 10:
        return "單次最多查詢 10 個幣種"

    # 批次解析 coin ID
    id_map: dict[str, str] = {}
    for sym in tickers:
        cid = _resolve_coin_id(sym.upper())
        if cid:
            id_map[sym.upper()] = cid

    if not id_map:
        return "找不到任何符合的幣種代號"

    ids_str = ",".join(id_map.values())
    try:
        resp = requests.get(
            COINGECKO_PRICE,
            headers=CG_HEADERS,
            params={
                "ids": ids_str,
                "vs_currencies": "usd",
                "include_24hr_change": "true",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return f"批次查詢失敗：{e}"

    results = []
    for sym, cid in id_map.items():
        row = data.get(cid, {})
        usd = row.get("usd")
        chg = row.get("usd_24h_change")
        if usd is None:
            results.append(f"【{sym}】查無資料")
            continue
        usd_str = f"${usd:,.6f}" if usd < 1 else f"${usd:,.2f}"
        arrow   = ""
        if chg is not None:
            arrow = f"  {'▲' if chg >= 0 else '▼'} {abs(chg):.2f}%"
        results.append(f"【{sym}】{usd_str} USD{arrow}")

    return "\n".join(results)


def get_exchange_rate(from_currency: str, to_currency: str = "TWD",
                      amount: float = 1.0) -> str:
    # 查詢即時匯率，支援主要貨幣代碼（USD、TWD、JPY、EUR 等）
    base = from_currency.strip().upper()
    target = to_currency.strip().upper()
    try:
        resp = requests.get(ER_URL.format(base=base), timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return f"匯率查詢失敗：{e}"

    if data.get("result") != "success":
        return f"不支援的貨幣代碼：{base}（請使用 ISO 4217 代碼，如 USD、TWD、JPY）"

    rates = data.get("rates", {})

    # 若 to_currency 為 "ALL"，回傳常用貨幣一覽
    COMMON = ["TWD", "USD", "EUR", "JPY", "CNY", "HKD", "GBP", "KRW", "SGD", "AUD"]
    if target == "ALL":
        lines = [f"【{base} 匯率一覽】"]
        for cur in COMMON:
            rate = rates.get(cur)
            if rate:
                converted = rate * amount
                lines.append(f"  {base} → {cur}：{rate:.4f}（{amount} {base} = {converted:.2f} {cur}）")
        return "\n".join(lines)

    rate = rates.get(target)
    if rate is None:
        return f"找不到 {target} 的匯率資料"

    converted = rate * amount
    update_time = data.get("time_last_update_utc", "")
    lines = [
        f"【{base} → {target}】",
        f"匯率：1 {base} = {rate:.4f} {target}",
        f"換算：{amount} {base} = {converted:,.4f} {target}",
    ]
    if update_time:
        lines.append(f"更新時間（UTC）：{update_time}")
    return "\n".join(lines)


# ── 工具定義（送給 Ollama 的 JSON Schema）──────────
DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_crypto_price",
            "description": (
                "查詢單一虛擬貨幣即時報價（美元＋台幣），含 24h 漲跌幅與市值。"
                "使用英文縮寫代號，如 BTC（比特幣）、ETH（以太坊）、SOL（Solana）、"
                "DOGE（狗狗幣）、XRP、ADA、AVAX 等"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "虛擬貨幣縮寫，如 BTC、ETH、SOL、DOGE",
                    },
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_multiple_cryptos",
            "description": "一次查詢多個虛擬貨幣報價，代號以逗號分隔，最多 10 個。例如：BTC,ETH,SOL",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbols": {
                        "type": "string",
                        "description": "虛擬貨幣代號，逗號分隔，例如：BTC,ETH,SOL,DOGE",
                    },
                },
                "required": ["symbols"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_exchange_rate",
            "description": (
                "查詢即時匯率並換算金額。支援主要貨幣 ISO 代碼：USD（美元）、TWD（台幣）、"
                "JPY（日圓）、EUR（歐元）、CNY（人民幣）、HKD（港幣）、GBP（英鎊）等。"
                "to_currency 填 ALL 可一次看常用貨幣一覽"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "from_currency": {
                        "type": "string",
                        "description": "來源貨幣代碼，例如：USD、TWD、JPY",
                    },
                    "to_currency": {
                        "type": "string",
                        "description": "目標貨幣代碼，預設 TWD；填 ALL 可看常用貨幣一覽",
                    },
                    "amount": {
                        "type": "number",
                        "description": "要換算的金額，預設 1",
                    },
                },
                "required": ["from_currency"],
            },
        },
    },
]

# ── 工具實作對照表 ─────────────────────────────────
IMPLEMENTATIONS = {
    "get_crypto_price":    get_crypto_price,
    "get_multiple_cryptos": get_multiple_cryptos,
    "get_exchange_rate":   get_exchange_rate,
}
