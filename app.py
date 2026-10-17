from flask import Flask, request, jsonify, render_template
from datetime import datetime
import os
import threading
import uuid
import requests

from config import SESSIONS_DIR
from session_manager import load_meta, save_meta, load_session, save_session, delete_session
from agent_runner import build_messages, agent_loop
from tools.github_trending import generate_weekly_report
import rag

app = Flask(__name__)


def _startup_weekly_report():
    # 啟動時背景執行：若本週週報尚未產生，自動抓取並翻譯後寫入 .md
    try:
        result = generate_weekly_report()
        print(f"[weekly] {result}")
    except Exception as e:
        print(f"[weekly] 週報產生失敗：{e}")


@app.route("/")
def index():
    # 回傳主頁面 HTML，所有 UI 邏輯都在 templates/index.html 的前端 JS 處理
    return render_template("index.html")


@app.route("/sessions", methods=["GET"])
def list_sessions():
    # 回傳所有 session 的 metadata 列表，前端用來顯示左側 session 清單
    # 按建立時間降冪排列（最新的在最上面）
    meta = load_meta()
    sessions = sorted(meta.values(), key=lambda x: x["created_at"], reverse=True)
    return jsonify(sessions)


@app.route("/sessions", methods=["POST"])
def new_session():
    # 建立新 session，id 格式：日期時間_隨機6碼（確保唯一性且可排序）
    sid = datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6]
    meta = load_meta()
    meta[sid] = {"id": sid, "title": "新對話", "created_at": datetime.now().isoformat()}
    save_meta(meta)
    save_session(sid, [])
    return jsonify(meta[sid])


@app.route("/sessions/<sid>", methods=["PATCH"])
def rename_session(sid):
    # 重新命名 session 標題（使用者手動改名時呼叫）
    title = request.json.get("title", "").strip()
    if not title:
        return jsonify({"error": "標題不能為空"}), 400
    meta = load_meta()
    if sid in meta:
        meta[sid]["title"] = title
        save_meta(meta)
    return jsonify({"ok": True})


@app.route("/sessions/<sid>", methods=["DELETE"])
def delete_session_route(sid):
    # 刪除指定 session 及其對話紀錄檔
    delete_session(sid)
    return jsonify({"ok": True})


@app.route("/sessions/<sid>/history", methods=["GET"])
def get_history(sid):
    # 回傳指定 session 的完整對話紀錄，前端切換 session 時用來還原對話顯示
    return jsonify(load_session(sid))


@app.route("/sessions/<sid>/clear", methods=["POST"])
def clear_session(sid):
    # 清空 session 的對話紀錄，但保留 session 本身（標題重設為「新對話」）
    save_session(sid, [])
    meta = load_meta()
    if sid in meta:
        meta[sid]["title"] = "新對話"
        save_meta(meta)
    return jsonify({"ok": True})


@app.route("/sessions/<sid>/chat", methods=["POST"])
def chat(sid):
    # 主要對話端點：接收使用者輸入，呼叫 agent_loop，回傳模型回答
    prompt    = request.json.get("prompt", "").strip()
    think     = request.json.get("think",  False)   # 是否開啟 think 模式（延伸思考）
    verify    = request.json.get("verify", False)   # 是否開啟驗證模式（答完再核查一次）
    image_b64 = request.json.get("image",  None)    # 使用者上傳的圖片（base64 字串）
    if not prompt and not image_b64:
        return jsonify({"error": "請輸入問題或上傳圖片"}), 400

    history  = load_session(sid)
    messages = build_messages(history, prompt, image_b64)

    try:
        reply = agent_loop(messages, think, verify)

        # 將本輪對話存入 session 紀錄與 RAG 向量資料庫
        turn_id = f"{sid}_turn_{len(history) // 2}"
        history.append({"role": "user",      "content": prompt})
        history.append({"role": "assistant", "content": reply})
        save_session(sid, history)
        rag.store_turn(turn_id, prompt, reply)

        # 第一輪自動以問題前 24 字當作 session 標題，方便識別
        meta = load_meta()
        if sid in meta and meta[sid]["title"] == "新對話":
            meta[sid]["title"] = prompt[:24] + ("…" if len(prompt) > 24 else "")
            save_meta(meta)

        # 回傳對話統計供前端顯示（總輪數、實際送給模型的輪數）
        total_turns = len(history) // 2
        return jsonify({
            "response":     reply,
            "total_turns":  total_turns,
            "active_turns": min(total_turns, 10),  # 最多 RECENT_TURNS 輪
            "title":        meta.get(sid, {}).get("title", ""),
        })
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "無法連接 Ollama，請確認服務已啟動"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    # debug=True 時 werkzeug reloader 會 fork：父 process 監控檔案、子 process 跑 Flask
    # 子 process 的環境變數 WERKZEUG_RUN_MAIN="true"，只在子 process 啟動背景任務
    # 避免兩個 process 同時呼叫 Ollama 翻譯（浪費資源且可能佔滿記憶體）
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        threading.Thread(target=_startup_weekly_report, daemon=True).start()
    app.run(host="127.0.0.1", port=5000, debug=True)
