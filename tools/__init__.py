from . import system, web, file_ops, pdf_ops, vision, weather, stock, calculator, chart, crypto, utils, github_trending

# 彙整所有模組的工具定義，格式符合 Ollama tool calling 的 JSON Schema
# 送給模型時讓它知道「有哪些工具可以呼叫、各自的參數是什麼」
TOOLS: list = (
    system.DEFINITIONS            +  # 系統工具：時間
    web.DEFINITIONS               +  # 網路工具：搜尋、爬蟲、RSS
    weather.DEFINITIONS           +  # 天氣工具：即時天氣與預報
    stock.DEFINITIONS             +  # 股票工具：台股＋美股報價
    crypto.DEFINITIONS            +  # 虛幣工具：CoinGecko 報價＋匯率
    calculator.DEFINITIONS        +  # 計算機工具：安全數學表達式求值
    chart.DEFINITIONS             +  # 圖表工具：股票走勢 PNG
    github_trending.DEFINITIONS   +  # GitHub 工具：本週熱門專案
    file_ops.DEFINITIONS          +  # 檔案工具：讀寫、CSV、刪除、搬移
    pdf_ops.DEFINITIONS           +  # PDF 工具：讀取、分頁、切割
    vision.DEFINITIONS            +  # 視覺工具：圖片分析
    utils.DEFINITIONS                # 雜項工具：剪貼簿、QR Code、IP 查詢
)

# 彙整所有模組的工具實作，key 為工具名稱字串，value 為可呼叫函式
# run_tool 透過這個字典根據名稱派送到正確的函式
TOOL_MAP: dict = {
    **system.IMPLEMENTATIONS,
    **web.IMPLEMENTATIONS,
    **weather.IMPLEMENTATIONS,
    **stock.IMPLEMENTATIONS,
    **crypto.IMPLEMENTATIONS,
    **calculator.IMPLEMENTATIONS,
    **chart.IMPLEMENTATIONS,
    **github_trending.IMPLEMENTATIONS,
    **file_ops.IMPLEMENTATIONS,
    **pdf_ops.IMPLEMENTATIONS,
    **vision.IMPLEMENTATIONS,
    **utils.IMPLEMENTATIONS,
}


def run_tool(name: str, args: dict) -> str:
    # 根據工具名稱找到對應函式並執行，回傳字串給模型
    # 所有工具都回傳字串，讓模型可以直接讀取結果並繼續思考
    fn = TOOL_MAP.get(name)
    if not fn:
        return f"未知工具：{name}"
    try:
        return str(fn(**args))
    except Exception as e:
        return f"工具執行錯誤：{e}"
