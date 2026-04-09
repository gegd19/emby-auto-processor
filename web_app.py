#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Emby Auto Processor Web 界面 - 完整版
- 支持配置管理、任务控制、实时日志
- 目录浏览 API
- 流式 AI 简介润色测试 (SSE)
"""

import os
import json
import time
import threading
import platform
from pathlib import Path
from flask import Flask, render_template, request, jsonify, Response, stream_with_context

# 导入核心处理模块
import emby_auto_processor as processor

app = Flask(__name__)
app.secret_key = os.urandom(24)

CONFIG_PATH = "auto_config.json"
LOG_FILE = "auto_processor_errors.log"

current_task = {
    "running": False,
    "progress": 0,
    "total": 0,
    "message": "",
    "log": []
}

def progress_callback(current, total, message, level="info"):
    current_task["progress"] = current
    current_task["total"] = total
    current_task["message"] = message
    current_task["log"].append({
        "msg": message,
        "level": level,
        "time": time.time()
    })
    if len(current_task["log"]) > 100:
        current_task["log"] = current_task["log"][-100:]

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/config', methods=['GET', 'POST'])
def config_api():
    if request.method == 'GET':
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                config = json.load(f)
            return jsonify(config)
        else:
            return jsonify(processor.DEFAULT_CONFIG)
    else:
        try:
            new_config = request.json
            with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(new_config, f, ensure_ascii=False, indent=2)
            return jsonify({"status": "success"})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/api/run', methods=['POST'])
def run_task():
    global current_task
    if current_task["running"]:
        return jsonify({"status": "error", "message": "已有任务在运行中"}), 400

    current_task.update({
        "running": True,
        "progress": 0,
        "total": 0,
        "message": "准备中...",
        "log": []
    })

    def task_wrapper():
        try:
            processor.run_processor_with_callback(CONFIG_PATH, progress_callback)
        except Exception as e:
            progress_callback(0, 0, f"任务异常: {e}", "error")
        finally:
            current_task["running"] = False
            current_task["message"] = "任务结束"

    threading.Thread(target=task_wrapper, daemon=True).start()
    return jsonify({"status": "started"})

@app.route('/api/status', methods=['GET'])
def get_status():
    return jsonify({
        "running": current_task["running"],
        "progress": current_task["progress"],
        "total": current_task["total"],
        "message": current_task["message"],
        "log": current_task["log"][-30:]
    })

@app.route('/api/log', methods=['GET'])
def get_full_log():
    if not os.path.exists(LOG_FILE):
        return jsonify({"log": ""})
    encodings = ['utf-8', 'gbk', 'cp1252', 'latin-1']
    content = ""
    for enc in encodings:
        try:
            with open(LOG_FILE, 'r', encoding=enc) as f:
                content = f.read()
            break
        except UnicodeDecodeError:
            continue
    if not content:
        with open(LOG_FILE, 'rb') as f:
            raw = f.read()
            content = raw.decode('utf-8', errors='replace')
    lines = content.splitlines()[-100:]
    return jsonify({"log": "\n".join(lines)})

# ---------- 目录浏览 ----------
@app.route('/api/drives', methods=['GET'])
def get_drives():
    if platform.system() == "Windows":
        drives = []
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            path = f"{letter}:\\"
            if os.path.exists(path):
                drives.append({"name": f"{letter}:", "path": path})
        return jsonify(drives)
    else:
        return jsonify([{"name": "/", "path": "/"}])

@app.route('/api/browse', methods=['GET'])
def browse_directory():
    req_path = request.args.get('path', '')
    if not req_path:
        return jsonify([])
    try:
        base_path = Path(req_path).resolve()
    except:
        return jsonify([])
    if not base_path.exists() or not base_path.is_dir():
        return jsonify([])
    parent = str(base_path.parent) if base_path.parent != base_path else None
    dirs = []
    try:
        for item in base_path.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                dirs.append({"name": item.name, "path": str(item)})
    except PermissionError:
        pass
    dirs.sort(key=lambda x: x["name"].lower())
    return jsonify({"current": str(base_path), "parent": parent, "dirs": dirs})

# ---------- 流式 AI 简介润色 ----------
@app.route('/api/ai/stream_enhance', methods=['POST'])
def stream_ai_enhance():
    """SSE 流式返回 AI 改写后的简介"""
    data = request.json
    title = data.get('title', '')
    original_plot = data.get('original_plot', '')
    ai_config = data.get('ai_config', {})

    if not title or not original_plot:
        return jsonify({"error": "缺少标题或简介"}), 400

    def generate():
        prompt_template = ai_config.get(
            'prompt_template',
            "你是一个专业的影视剧文案。请将以下剧集简介改写得更加生动、吸引人，语言流畅自然，可以适当增加一些悬念和感染力。请直接输出改写后的简介，不要添加额外说明。\n\n原标题：{title}\n原简介：{original_plot}\n\n优化后简介："
        )
        prompt = prompt_template.format(title=title, original_plot=original_plot)

        provider = ai_config.get("provider", "deepseek")
        api_key = ai_config.get("api_key")
        model = ai_config.get("model", "deepseek-chat")
        base_url = ai_config.get("base_url", "https://api.deepseek.com")
        temperature = ai_config.get("temperature", 0.7)
        max_tokens = ai_config.get("max_tokens", 500)

        url_map = {
            "deepseek": f"{base_url}/v1/chat/completions",
            "openai": "https://api.openai.com/v1/chat/completions",
            "zhipu": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
            "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        }
        url = url_map.get(provider)
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True
        }

        try:
            session = processor.create_retry_session()
            resp = session.post(url, headers=headers, json=payload, stream=True, timeout=60)
            resp.raise_for_status()

            for line in resp.iter_lines(decode_unicode=True):
                if line and line.startswith("data: "):
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        content = chunk['choices'][0]['delta'].get('content', '')
                        if content:
                            yield f"data: {json.dumps({'content': content})}\n\n"
                    except:
                        continue
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')

if __name__ == '__main__':
    if not hasattr(processor, 'run_processor_with_callback'):
        print("错误：emby_auto_processor.py 缺少 run_processor_with_callback 函数。")
        exit(1)
    app.run(host='0.0.0.0', port=5000, debug=False)