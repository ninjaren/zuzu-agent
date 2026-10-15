import json
import requests
from config import MODEL, OLLAMA_URL, RECENT_TURNS, RAG_TOP_K, SYSTEM_PROMPT
from tools import TOOLS, run_tool
from tools.web import reset_browse_counts
from tools.vision import analyze_image_b64
import rag


def build_messages(history: list, query: str, image_b64: str = None) -> list:
    # 組合送給模型的完整訊息列表：
    #   1. system prompt（角色定義與規則）
    #   2. RAG 過去相關對話（語意搜尋找出相關紀錄，但排除已在 recent 中的）
    #   3. 最近 N 輪對話（提供短期記憶）
    #   4. 本次使用者提問（可附帶圖片描述）
    recent = history[-(RECENT_TURNS * 2):]
    recent_texts = {m["content"] for m in recent}

    # 從 ChromaDB 語意搜尋過去對話，過濾掉已在 recent 中的重複內容
    retrieved = rag.retrieve(query, top_k=RAG_TOP_K)
    relevant = [
        f"Q: {t['user']}\nA: {t['assistant']}"
        for t in retrieved
        if t["user"] not in recent_texts
    ]

    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    if relevant:
        # 將 RAG 結果以獨立 system 訊息注入，不污染對話流
        msgs.append({
            "role": "system",
            "content": "以下是過去相關的對話紀錄，供你參考：\n\n" + "\n\n---\n\n".join(relevant),
        })
    msgs.extend(recent)

    # 有圖片時：先用 llava 將圖片轉成文字描述，再帶入給 qwen3 一起理解
    # qwen3:8b 沒有原生視覺能力，這是雙模型協作的橋接方式
    if image_b64:
        description = analyze_image_b64(image_b64, query or "請詳細描述這張圖片的內容")
        msgs.append({
            "role": "user",
            "content": f"[圖片分析結果]\n{description}\n\n使用者問題：{query}" if query else f"[圖片分析結果]\n{description}",
        })
    else:
        msgs.append({"role": "user", "content": query})

    return msgs


def agent_loop(messages: list, think: bool) -> str:
    # 每次新對話重設 browse 計數器，讓新對話有完整的 5 次配額
    reset_browse_counts()

    # 持續呼叫 Ollama 直到模型不再要求工具，才回傳最終回答
    # 迴圈流程：
    #   模型回應 → 有 tool_calls → 執行工具 → 把結果加入訊息 → 再呼叫模型
    #   模型回應 → 無 tool_calls → 回傳最終文字答案，結束迴圈
    while True:
        resp = requests.post(
            OLLAMA_URL,
            json={"model": MODEL, "messages": messages, "tools": TOOLS, "stream": False, "think": think},
            timeout=120,
        )
        resp.raise_for_status()
        msg = resp.json()["message"]
        messages.append(msg)  # 把模型回應加入訊息串，維持對話上下文

        # 模型沒有要求工具 → 這是最終回答
        if not msg.get("tool_calls"):
            return msg["content"]

        # 執行模型要求的每個工具，將結果以 role="tool" 訊息回傳給模型
        for tc in msg["tool_calls"]:
            name = tc["function"]["name"]
            args = tc["function"]["arguments"]
            if isinstance(args, str):
                args = json.loads(args)  # Ollama 有時回傳 JSON 字串而非 dict
            messages.append({"role": "tool", "content": run_tool(name, args)})
