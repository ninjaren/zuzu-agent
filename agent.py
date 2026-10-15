"""
standalone 終端機模式，直接執行 python agent.py 可在命令列與 ZuZu 對話。
Web 介面請用 python app.py。
"""
import json
import requests
from config import MODEL, OLLAMA_URL, SYSTEM_PROMPT
from tools import TOOLS, run_tool


def agent(user_input: str):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_input},
    ]

    while True:
        resp = requests.post(
            OLLAMA_URL,
            json={"model": MODEL, "messages": messages, "tools": TOOLS, "stream": False},
            timeout=120,
        )
        resp.raise_for_status()
        msg = resp.json()["message"]
        messages.append(msg)

        if not msg.get("tool_calls"):
            print(f"\n回答：{msg['content']}")
            break

        for tc in msg["tool_calls"]:
            name = tc["function"]["name"]
            args = tc["function"]["arguments"]
            if isinstance(args, str):
                args = json.loads(args)
            print(f"\n[呼叫工具] {name}  參數：{args}")
            result = run_tool(name, args)
            print(f"[工具結果] {result[:300]}")
            messages.append({"role": "tool", "content": result})


if __name__ == "__main__":
    from tools import TOOL_MAP
    print(f"ZuZu 終端機模式（Ctrl+C 離開）")
    print(f"可用工具：{', '.join(TOOL_MAP.keys())}\n")
    while True:
        try:
            q = input("你：").strip()
            if q:
                agent(q)
        except KeyboardInterrupt:
            print("\n關閉")
            break
