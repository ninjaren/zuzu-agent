import requests
from urllib.parse import quote

# wttr.in 免費天氣 API，不需要 API Key，支援城市名稱或座標
WTTR_URL = "https://wttr.in/{location}?format=j1&lang=zh-tw"


# wttr.in 部分天氣描述沒有中文翻譯，補充常見對照
_WEATHER_ZH = {
    "Sunny": "晴天", "Clear": "晴朗", "Partly cloudy": "晴時多雲",
    "Cloudy": "多雲", "Overcast": "陰天", "Mist": "薄霧", "Fog": "霧",
    "Light rain": "小雨", "Moderate rain": "中雨", "Heavy rain": "大雨",
    "Light drizzle": "毛毛雨", "Freezing drizzle": "凍雨",
    "Patchy rain nearby": "局部有雨", "Patchy rain possible": "局部可能有雨",
    "Thundery outbreaks possible": "可能有雷陣雨",
    "Blowing snow": "吹雪", "Light snow": "小雪", "Moderate snow": "中雪",
    "Heavy snow": "大雪", "Blizzard": "暴風雪",
    "Light sleet": "小凍雨", "Moderate or heavy sleet": "中到大凍雨",
    "Light showers of ice pellets": "輕度冰雹", "Ice pellets": "冰雹",
}


def _zh_desc(desc: str) -> str:
    # 先查對照表，找不到才回傳原文
    return _WEATHER_ZH.get(desc, desc)


def get_weather(location: str) -> str:
    # 查詢指定地點的目前天氣與今日預報
    # 支援中文城市（台北）、英文（Taipei）、機場代碼（TPE）
    try:
        url = WTTR_URL.format(location=quote(location))
        # wttr.in 對 curl UA 更友善，避免被當成瀏覽器爬蟲
        headers = {"User-Agent": "curl/7.68.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return f"天氣查詢失敗：{e}"

    try:
        cur   = data["current_condition"][0]
        today = data["weather"][0]
        astro = today["astronomy"][0]

        lang_key = "lang_zh-tw"
        en_desc = cur["weatherDesc"][0]["value"]
        # 對照表優先，找不到才用 wttr.in 的翻譯（可能仍是英文）
        desc = _zh_desc(en_desc) if en_desc in _WEATHER_ZH else (
            cur.get(lang_key, [{}])[0].get("value") or en_desc
        )

        temp    = cur["temp_C"]
        feels   = cur["FeelsLikeC"]
        humid   = cur["humidity"]
        wind_kph= cur["windspeedKmph"]
        wind_dir= cur["winddir16Point"]
        uv      = cur.get("uvIndex", "N/A")
        vis     = cur.get("visibility", "N/A")

        max_t   = today["maxtempC"]
        min_t   = today["mintempC"]
        sunrise = astro["sunrise"]
        sunset  = astro["sunset"]

        lines = [
            f"【{location}】目前天氣",
            f"天氣狀況：{desc}",
            f"氣溫：{temp}°C（體感 {feels}°C）",
            f"今日最高／最低：{max_t}°C／{min_t}°C",
            f"濕度：{humid}%　風向：{wind_dir}　風速：{wind_kph} km/h",
            f"UV 指數：{uv}　能見度：{vis} km",
            f"日出：{sunrise}　日落：{sunset}",
        ]

        # 逐時預報：wttr.in 每 3 小時一筆，共 8 個時間點（00:00 - 21:00）
        hourly = today.get("hourly", [])
        if hourly:
            lines.append("\n逐時預報：")
            for h in hourly:
                t = int(h["time"]) // 100
                h_en = h["weatherDesc"][0]["value"]
                h_desc = _zh_desc(h_en) if h_en in _WEATHER_ZH else (
                    h.get(lang_key, [{}])[0].get("value") or h_en
                )
                rain_pct = h.get("chanceofrain", "0")
                lines.append(f"  {t:02d}:00　{h['tempC']}°C　{h_desc}　降雨機率 {rain_pct}%")

        # 未來兩天預報
        if len(data["weather"]) >= 3:
            lines.append("\n未來天氣：")
            for day in data["weather"][1:3]:
                raw_desc = (day["hourly"][4]["weatherDesc"][0]["value"]
                            if day.get("hourly") else "")
                d_desc = (day["hourly"][4].get(lang_key, [{}])[0].get("value")
                          or _zh_desc(raw_desc)) if day.get("hourly") else ""
                lines.append(
                    f"  {day['date']}　最高 {day['maxtempC']}°C / 最低 {day['mintempC']}°C　{d_desc}"
                )

        return "\n".join(lines)

    except (KeyError, IndexError) as e:
        return f"天氣資料解析失敗：{e}（原始回應可能格式異常）"


# ── 工具定義（送給 Ollama 的 JSON Schema）──────────
DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查詢指定地點的目前天氣、今日溫度範圍、濕度、風速、UV 指數與未來兩天預報。支援中文城市名稱（台北）、英文（Taipei）或機場代碼（TPE）",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "要查詢天氣的地點，例如：台北、高雄、Tokyo、New York",
                    },
                },
                "required": ["location"],
            },
        },
    },
]

# ── 工具實作對照表 ─────────────────────────────────
IMPLEMENTATIONS = {
    "get_weather": get_weather,
}
