#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Emby 全自动入库工具 v4.0 最终全能版
- 支持电影和剧集智能识别
- 电影 → 调用 TMDB Movie API，放入独立电影目录
- 剧集 → 调用 TMDB TV API，放入剧集目录
- AI 解析增强（支持全局集号修正） + 详细日志 + 增量缓存 + Web 界面支持
- 导出 create_retry_session 供 Web 流式路由使用
- 优化：AI 提示词增强、多别名搜索、跨设备回退、线程安全等
"""

import os
import re
import json
import time
import hashlib
import argparse
import platform
import logging
import threading
import requests
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

# ---------- 全局缓存变量 ----------
_tv_details_cache = {}
_tv_seasons_cache = {}
_tv_details_lock = threading.Lock()
_tv_seasons_lock = threading.Lock()

logging.basicConfig(
    filename="auto_processor_errors.log",
    level=logging.ERROR,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

CONFIG_FILE = "auto_config.json"
CACHE_FILE = "auto_processed_cache.json"

DEFAULT_CONFIG = {
    "source_folders": ["D:/movie"],
    "tv_target_folder": "D:/Emby_Media/TV Shows",
    "movie_target_folder": "D:/Emby_Media/Movies",
    "video_extensions": [".mkv", ".mp4", ".avi", ".ts", ".m2ts", ".mov", ".wmv", ".flv"],
    "link_type": "hard",
    "ignore_patterns": ["sample", "trailer", "extra"],
    "min_file_size_mb": 0,
    "dry_run": False,
    "add_year_to_folder": True,
    "force_chinese_name": True,
    "incremental": True,
    "max_workers": 3,
    "download_images": True,
    "image_base_url": "https://image.tmdb.org/t/p/original",
    "tmdb_api": {"api_key": "YOUR_TMDB_API_KEY_V3", "language": "zh-CN"},
    "ai_parser": {
        "enabled": False,
        "provider": "deepseek",
        "api_key": "YOUR_API_KEY",
        "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com",
        "temperature": 0.1,
        "max_tokens": 600,
        "timeout": 20,
        "debug": False
    },
    "ai_plot_enhance": {
        "enabled": False,
        "provider": "deepseek",
        "api_key": "YOUR_API_KEY",
        "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com",
        "temperature": 0.7,
        "max_tokens": 500,
        "timeout": 30,
        "prompt_template": "你是一个专业的影视剧文案。请将以下剧情简介改写得更加生动、吸引人，语言流畅自然，可以适当增加一些悬念和感染力。请直接输出改写后的简介，不要添加额外说明。\n\n原标题：{title}\n原简介：{original_plot}\n\n优化后简介："
    }
}

# 全局停止标志（用于 Web 界面停止任务）
stop_processing = threading.Event()

cache_lock = threading.Lock()
ai_cache_lock = threading.Lock()  # 保护 AI_CACHE 的线程安全
AI_CACHE = {}

LOG_INFO = "info"
LOG_SUCCESS = "success"
LOG_ERROR = "error"
LOG_WARNING = "warning"
LOG_PROGRESS = "progress"

# ==================== 配置与缓存 ====================
def load_config(config_path: str = CONFIG_FILE) -> dict:
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            user_config = json.load(f)
            merged = DEFAULT_CONFIG.copy()
            for k, v in user_config.items():
                if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
                    merged[k] = {**merged[k], **v}
                else:
                    merged[k] = v
            return merged
    else:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
        return DEFAULT_CONFIG

def load_cache() -> Dict[str, dict]:
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_cache(cache: Dict[str, dict]):
    with cache_lock:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)

def get_file_fingerprint(filepath: Path) -> str:
    stat = filepath.stat()
    raw = f"{str(filepath.resolve())}|{stat.st_size}|{stat.st_mtime}"
    return hashlib.md5(raw.encode()).hexdigest()

def is_already_processed(src: Path, cache_entry: dict, config: dict, log_func=None) -> bool:
    target = Path(cache_entry.get("target", ""))
    if not target.exists():
        return False
    current_fp = get_file_fingerprint(src)
    if cache_entry.get("fingerprint") != current_fp:
        return False
    try:
        if config["link_type"] == "hard":
            return os.path.samefile(src, target)
        else:
            return target.resolve() == src.resolve()
    except:
        return False

# ==================== 工具函数 ====================
def get_long_path(path: Path) -> str:
    if platform.system() == "Windows":
        abs_path = str(path.resolve())
        if not abs_path.startswith("\\\\?\\"):
            return "\\\\?\\" + abs_path
        return abs_path
    return str(path)

def sanitize_filename(name: str) -> str:
    if not name:
        return "Unknown"
    return re.sub(r'[\\/*?:"<>|]', '_', name).strip()

def is_video_file(filepath: Path, config: dict) -> bool:
    ext = filepath.suffix.lower()
    allowed = [e.lower() for e in config["video_extensions"]]
    if ext not in allowed:
        return False
    name_lower = filepath.stem.lower()
    for pattern in config["ignore_patterns"]:
        if re.search(rf'\b{re.escape(pattern.lower())}\b', name_lower):
            return False
    min_mb = config.get("min_file_size_mb", 0)
    if min_mb > 0:
        try:
            if filepath.stat().st_size / (1024 * 1024) < min_mb:
                return False
        except:
            return False
    return True

def create_retry_session() -> requests.Session:
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
    session.mount('https://', HTTPAdapter(max_retries=retries))
    return session

# ==================== AI 调用 ====================
def call_ai_api(prompt: str, ai_config: dict, log_func=None) -> Optional[str]:
    provider = ai_config.get("provider", "deepseek")
    api_key = ai_config.get("api_key")
    model = ai_config.get("model")
    base_url = ai_config.get("base_url", "https://api.deepseek.com")
    temperature = ai_config.get("temperature", 0.7)
    max_tokens = ai_config.get("max_tokens", 500)
    timeout = ai_config.get("timeout", 30)

    url_map = {
        "deepseek": f"{base_url}/v1/chat/completions",
        "openai": "https://api.openai.com/v1/chat/completions",
        "zhipu": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    }
    url = url_map.get(provider)
    if not url:
        if log_func:
            log_func(f"❌ 不支持的 AI 提供商: {provider}", LOG_ERROR)
        return None

    if log_func:
        log_func(f"🤖 调用 AI API: {provider} 模型 {model}", LOG_INFO)

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": temperature, "max_tokens": max_tokens}
    session = create_retry_session()
    try:
        start = time.time()
        resp = session.post(url, headers=headers, json=payload, timeout=timeout)
        resp.raise_for_status()
        elapsed = time.time() - start
        if log_func:
            log_func(f"✅ AI 响应成功 ({elapsed:.2f}s)", LOG_SUCCESS)
        if ai_config.get("debug") and log_func:
            log_func(f"📝 AI 原始响应: {resp.text[:500]}", LOG_INFO)
        return resp.json()['choices'][0]['message']['content'].strip()
    except Exception as e:
        if log_func:
            log_func(f"❌ AI API 调用失败: {e}", LOG_ERROR)
        return None

# ==================== AI 智能解析（增强版：支持全局集号修正） ====================
def parse_filename_with_ai(filename: str, config: dict, log_func=None) -> dict:
    ai_cfg = config.get("ai_parser", {})
    if log_func:
        log_func(f"🤖 AI 解析文件名: {filename[:80]}...", LOG_INFO)

    force_chinese = config.get("force_chinese_name", True)
    prompt = f"""你是一个专业的影视媒体文件名解析专家。请分析以下视频文件名，提取准确的元数据，并以严格 JSON 格式返回。

文件名：{filename}

要求：
1. media_type: "movie" 或 "tv"（严格区分，剧集必须包含季/集标识，如 S01E02、第1季第2集、EP02 等；否则为 movie）
2. title: 影视的规范中文名（如果可能）或原始英文名。如果是剧集，使用剧集的主标题，不要包含季/集信息。
3. year: 发行年份（四位数字）。若文件名中包含年份（如 2022、1994），则提取；否则根据你的知识推断常见年份，如果实在不确定则设为 null。
4. season: 季号（整数，仅剧集需要，若无则为 null）。注意：单季剧集如果未标注季号，默认为 1。
5. episode: 集号（整数，仅剧集需要，若无则为 null）。
6. episode_title: 单集标题（如果文件名中包含明显的集标题，否则为空字符串）。
7. alternative_titles: 数组，提供可能的别名（包括英文名、中文名、其他地区常用名），至少提供 1-3 个别名，帮助提高 TMDB 搜索命中率。
8. year_guess: 如果你推断的年份不确定，可以提供一个推测年份（整数），否则为 null。
9. **智能修正全局集号**：有些剧集的命名使用全局递增集号（例如第一季有 25 集，第二季的第一集被命名为 S02E26 而不是 S02E01）。请根据你的常识判断是否存在这种情况，如果存在，则提供修正后的季号 `corrected_season` 和集号 `corrected_episode`，否则这两个字段设为 null。
   - 例如：文件名 `间谍过家家 S02E26`，你已知第一季通常为 25 集，那么应该推断出实际为第二季的第 1 集，输出 `"corrected_season": 2, "corrected_episode": 1`。
   - 如果文件名已经是规范季内编号（如 S02E01），则 `corrected_season` 和 `corrected_episode` 为 null。

注意：
- 忽略压制组、分辨率、音视频编码等无关标签（如 1080p, x264, WEB-DL, AMZN, NF, 字幕组等）。
- 如果文件名中既有中文又有英文，优先使用中文作为 title，英文放入 alternative_titles。
- 只返回合法 JSON，不要任何解释或额外文本。

返回示例（剧集，需要修正）：
{{
  "media_type": "tv",
  "title": "间谍过家家",
  "year": 2022,
  "season": 2,
  "episode": 26,
  "episode_title": "",
  "alternative_titles": ["Spy x Family", "SPY×FAMILY"],
  "year_guess": null,
  "corrected_season": 2,
  "corrected_episode": 1
}}

返回示例（剧集，无需修正）：
{{
  "media_type": "tv",
  "title": "权力的游戏",
  "year": 2011,
  "season": 1,
  "episode": 1,
  "episode_title": "凛冬将至",
  "alternative_titles": ["Game of Thrones", "冰与火之歌"],
  "year_guess": null,
  "corrected_season": null,
  "corrected_episode": null
}}

返回示例（电影）：
{{
  "media_type": "movie",
  "title": "肖申克的救赎",
  "year": 1994,
  "season": null,
  "episode": null,
  "episode_title": "",
  "alternative_titles": ["The Shawshank Redemption", "刺激1995"],
  "year_guess": null,
  "corrected_season": null,
  "corrected_episode": null
}}

请严格按照上述 JSON 格式返回，不要添加注释。"""
    resp = call_ai_api(prompt, ai_cfg, log_func)
    if not resp:
        return {"media_type": "unknown"}

    try:
        start = resp.find('{')
        end = resp.rfind('}')
        json_str = resp[start:end+1] if (start != -1 and end != -1) else resp.strip().strip('`').strip('json')
        data = json.loads(json_str)
        # 确保必要的字段存在
        data.setdefault("alternative_titles", [])
        data.setdefault("year_guess", None)
        data.setdefault("corrected_season", None)
        data.setdefault("corrected_episode", None)
        return data
    except Exception as e:
        if log_func:
            log_func(f"❌ AI 响应解析失败: {e}", LOG_ERROR)
        return {"media_type": "unknown"}

def parse_filename_regex(filename: str) -> dict:
    name = Path(filename).stem
    name = re.sub(r'\.\.\w+$', '', name)
    name = re.sub(r'^\[[^\]]+\]\s*', '', name)
    year = re.search(r'\b(19|20)\d{2}\b', name)
    year = year.group(0) if year else None

    # 检测季集标识
    tv_patterns = [
        r'[Ss](\d{1,2})[Ee](\d{1,2})',
        r'(\d{1,2})[xX](\d{1,2})',
        r'第\s*(\d{1,2})\s*季\s*第\s*(\d{1,2})\s*集',
        r'\[(\d{1,2})\]'
    ]
    season, episode = None, None
    for p in tv_patterns:
        m = re.search(p, name, re.I)
        if m:
            if p in [r'[Ss](\d{1,2})[Ee](\d{1,2})', r'(\d{1,2})[xX](\d{1,2})', r'第\s*(\d{1,2})\s*季\s*第\s*(\d{1,2})\s*集']:
                season, episode = int(m.group(1)), int(m.group(2))
            else:
                season, episode = 1, int(m.group(1))
            break

    media_type = "tv" if episode is not None else "movie"

    # 清理名称 - 保留完整标题
    name = re.sub(r'[\[\]\(\)【】_,\.-]', ' ', name)
    name = re.sub(r'\b(1080p|720p|4K|HDR|HEVC|x264|x265|AAC|WEB-DL|BluRay)\b', '', name, flags=re.I)
    name = re.sub(r'\s+', ' ', name).strip()
    title = name if name else Path(filename).stem.split('.')[0]
    if not re.search(r'[\u4e00-\u9fff]', title):
        eng = re.search(r'[A-Za-z0-9!]+(?:\s+[A-Za-z0-9!]+)*', title)
        if eng:
            title = eng.group(0)

    return {
        "media_type": media_type,
        "title": title,
        "year": year,
        "season": season,
        "episode": episode,
        "episode_title": "",
        "alternative_titles": [],
        "year_guess": None,
        "corrected_season": None,
        "corrected_episode": None
    }

def parse_filename(filename: str, config: dict, log_func=None) -> dict:
    with ai_cache_lock:
        if filename in AI_CACHE:
            return AI_CACHE[filename]
    result = {"media_type": "unknown", "title": None, "year": None, "season": None, "episode": None, "episode_title": "", "alternative_titles": [], "year_guess": None, "corrected_season": None, "corrected_episode": None}

    if config.get("ai_parser", {}).get("enabled"):
        ai_res = parse_filename_with_ai(filename, config, log_func)
        if ai_res.get("media_type") in ("movie", "tv"):
            result.update(ai_res)
            if not isinstance(result.get("alternative_titles"), list):
                result["alternative_titles"] = []
            # 清理 title 中可能残留的季集信息
            if result["media_type"] == "tv" and result["title"]:
                result["title"] = re.sub(r'\s*[Ss]\d+.*$', '', result["title"]).strip()
            with ai_cache_lock:
                AI_CACHE[filename] = result
            return result

    # fallback 到正则
    regex_res = parse_filename_regex(filename)
    result.update(regex_res)
    with ai_cache_lock:
        AI_CACHE[filename] = result
    return result

# ==================== AI 英文翻译 ====================
def get_english_name_from_ai(chinese_name: str, config: dict, log_func=None):
    if not config.get("ai_parser", {}).get("enabled"):
        return None
    if log_func:
        log_func(f"🤖 请求 AI 翻译英文名: {chinese_name}", LOG_INFO)
    resp = call_ai_api(f"请将以下中文影视名称翻译为英文原名，只返回英文名：{chinese_name}", config["ai_parser"], log_func)
    if not resp:
        return None
    cleaned = re.sub(r'^(Original English Title|英文原名|English Name)[:\s]*', '', resp, flags=re.IGNORECASE).strip()
    return cleaned if cleaned else resp.strip()

# ==================== AI 简介美化 ====================
PLOT_CACHE = {}
plot_cache_lock = threading.Lock()

def enhance_plot(title: str, original_plot: str, config: dict, log_func=None) -> str:
    if not original_plot or original_plot == "暂无简介":
        return original_plot
    key = f"{title}|{original_plot}"
    with plot_cache_lock:
        if key in PLOT_CACHE:
            return PLOT_CACHE[key]
    if not config.get("ai_plot_enhance", {}).get("enabled"):
        return original_plot
    if log_func:
        log_func(f"🤖 AI 改写简介: {title}", LOG_INFO)
    prompt = config["ai_plot_enhance"]["prompt_template"].format(title=title, original_plot=original_plot)
    start = time.time()
    enhanced = call_ai_api(prompt, config["ai_plot_enhance"], log_func)
    if enhanced:
        with plot_cache_lock:
            PLOT_CACHE[key] = enhanced
        if log_func:
            log_func(f"✅ 简介改写完成 ({time.time()-start:.2f}s)", LOG_SUCCESS)
        return enhanced
    return original_plot

# ==================== TMDB 搜索（增强版，支持别名和多策略） ====================
def search_tmdb(media_type: str, query: str, year: Optional[str], config: dict, log_func=None, alt_titles=None) -> Optional[Dict]:
    api_key = config["tmdb_api"]["api_key"]
    lang = config["tmdb_api"].get("language", "zh-CN")
    url = f"https://api.themoviedb.org/3/search/{media_type}"

    # 构建搜索队列
    search_terms = []
    if query:
        search_terms.append(query)
        # 去除标点符号
        search_terms.append(re.sub(r'[！!？?\-—:;，。、~@#$%^&*()_+={}\[\]|\\:;"\'<>,./]', '', query))
    if alt_titles:
        for alt in alt_titles:
            if alt and alt != query:
                search_terms.append(alt)
                search_terms.append(re.sub(r'[！!？?\-—:;，。、~@#$%^&*()_+={}\[\]|\\:;"\'<>,./]', '', alt))
    # 从 query 中提取纯英文部分（如果包含中文）
    if query and re.search(r'[\u4e00-\u9fff]', query):
        eng_part = re.sub(r'[\u4e00-\u9fff]', '', query).strip()
        if eng_part:
            search_terms.append(eng_part)

    # 去重，保持顺序
    seen = set()
    unique_terms = []
    for term in search_terms:
        if term not in seen and len(term) > 1:
            seen.add(term)
            unique_terms.append(term)

    def _search(q, y):
        params = {"api_key": api_key, "query": q, "language": lang}
        if y and y != "null" and y != "None":
            if media_type == "movie":
                params["primary_release_year"] = y
            else:
                params["first_air_date_year"] = y
        if log_func:
            log_func(f"🌐 TMDB {media_type.upper()}: GET {url}?query={q}&year={y}", LOG_INFO)
        try:
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            results = resp.json().get("results", [])
            if results:
                return results[0]
        except Exception as e:
            if log_func:
                log_func(f"⚠️ TMDB 请求失败: {e}", LOG_WARNING)
        return None

    # 年份优先级：传入的 year -> 无年份
    years_to_try = [year] if year and year != "null" else [None]

    # 先尝试有年份的搜索
    for term in unique_terms:
        for y in years_to_try:
            result = _search(term, y)
            if result:
                return result
        # 再尝试无年份搜索（如果上面已经试过 None，这里避免重复）
        if None not in years_to_try:
            result = _search(term, None)
            if result:
                return result

    # 如果都没找到，最后尝试使用 language 为 en 再搜一次英文标题
    if lang != "en":
        params = {"api_key": api_key, "query": query, "language": "en"}
        try:
            resp = requests.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                if results:
                    if log_func:
                        log_func(f"🌐 TMDB 英文搜索成功: {results[0].get('title')}", LOG_SUCCESS)
                    return results[0]
        except:
            pass

    if log_func:
        log_func(f"❌ TMDB 搜索无结果: {query}", LOG_ERROR)
    return None

def get_tmdb_details(media_type: str, tmdb_id: int, config: dict, log_func=None):
    if media_type == "tv":
        with _tv_details_lock:
            if tmdb_id in _tv_details_cache:
                if log_func:
                    log_func(f"📦 使用缓存: tv/{tmdb_id}", LOG_INFO)
                return _tv_details_cache[tmdb_id]
    url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}"
    params = {"api_key": config["tmdb_api"]["api_key"], "language": config["tmdb_api"].get("language", "zh-CN")}
    if log_func:
        log_func(f"🌐 获取详情: GET {url}", LOG_INFO)
    try:
        resp = requests.get(url, params=params, timeout=15)
        data = resp.json()
        if media_type == "tv":
            with _tv_details_lock:
                _tv_details_cache[tmdb_id] = data
        return data
    except Exception as e:
        if log_func:
            log_func(f"❌ 获取详情失败: {e}", LOG_ERROR)
        return None

def get_tv_season_episodes(tv_id: int, season_num: int, config: dict, log_func=None):
    cache_key = (tv_id, season_num)
    with _tv_seasons_lock:
        if cache_key in _tv_seasons_cache:
            if log_func:
                log_func(f"📦 使用缓存: tv/{tv_id}/season/{season_num}", LOG_INFO)
            return _tv_seasons_cache[cache_key]
    url = f"https://api.themoviedb.org/3/tv/{tv_id}/season/{season_num}"
    params = {"api_key": config["tmdb_api"]["api_key"], "language": config["tmdb_api"].get("language", "zh-CN")}
    try:
        resp = requests.get(url, params=params, timeout=15)
        data = resp.json()
        episodes = data.get("episodes", [])
        with _tv_seasons_lock:
            _tv_seasons_cache[cache_key] = episodes
        return episodes
    except Exception as e:
        if log_func:
            log_func(f"❌ 获取季信息失败: {e}", LOG_ERROR)
        return []

# ==================== 图片下载 ====================
def download_image(url: str, save_path: Path, log_func=None) -> bool:
    if save_path.exists():
        return True
    try:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        if log_func:
            log_func(f"⬇️ 下载图片: {save_path.name}", LOG_INFO)
        session = create_retry_session()
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        with open(save_path, 'wb') as f:
            f.write(resp.content)
        if log_func:
            log_func(f"✅ 图片下载完成", LOG_SUCCESS)
        return True
    except Exception as e:
        if log_func:
            log_func(f"❌ 图片下载失败: {e}", LOG_ERROR)
        return False

# ==================== NFO 生成 ====================
def write_movie_nfo(movie_dir: Path, title: str, tmdb_id: int, overview: str, year: str, config: dict, log_func=None):
    movie_dir.mkdir(parents=True, exist_ok=True)
    nfo = movie_dir / "movie.nfo"
    if nfo.exists():
        return
    if config.get("ai_plot_enhance", {}).get("enabled"):
        overview = enhance_plot(title, overview, config, log_func)
    root = Element("movie")
    SubElement(root, "title").text = title
    SubElement(root, "plot").text = overview or ""
    if year and year != "0000":
        SubElement(root, "year").text = year
    SubElement(root, "uniqueid", type="tmdb", default="true").text = str(tmdb_id)
    with open(nfo, 'w', encoding='utf-8') as f:
        f.write(minidom.parseString(tostring(root, 'utf-8')).toprettyxml(indent="  "))
    if log_func:
        log_func(f"📄 写入 movie.nfo", LOG_INFO)

def write_tvshow_nfo(show_dir: Path, title: str, tmdb_id: int, overview: str, year: str, num_seasons: int, config: dict, log_func=None):
    show_dir.mkdir(parents=True, exist_ok=True)
    nfo = show_dir / "tvshow.nfo"
    if nfo.exists():
        return
    if config.get("ai_plot_enhance", {}).get("enabled"):
        overview = enhance_plot(title, overview, config, log_func)
    root = Element("tvshow")
    SubElement(root, "title").text = title
    SubElement(root, "plot").text = overview or ""
    if year and year != "0000":
        SubElement(root, "premiered").text = f"{year}-01-01"
    SubElement(root, "uniqueid", type="tmdb", default="true").text = str(tmdb_id)
    SubElement(root, "numseasons").text = str(num_seasons)
    with open(nfo, 'w', encoding='utf-8') as f:
        f.write(minidom.parseString(tostring(root, 'utf-8')).toprettyxml(indent="  "))
    if log_func:
        log_func(f"📄 写入 tvshow.nfo", LOG_INFO)

def write_season_nfo(season_dir: Path, season_num: int, tv_id: int, log_func=None):
    season_dir.mkdir(parents=True, exist_ok=True)
    nfo = season_dir / "season.nfo"
    if nfo.exists():
        return
    root = Element("season")
    SubElement(root, "seasonnumber").text = str(season_num)
    SubElement(root, "uniqueid", type="tmdb", default="true").text = f"{tv_id}/{season_num}"
    with open(nfo, 'w', encoding='utf-8') as f:
        f.write(minidom.parseString(tostring(root, 'utf-8')).toprettyxml(indent="  "))

def write_episode_nfo(ep_dir: Path, ep_data: dict, show_title: str, season: int, ep_num: int, tv_id: int, config: dict, log_func=None):
    ep_dir.mkdir(parents=True, exist_ok=True)
    safe_title = sanitize_filename(ep_data.get("name", f"Episode {ep_num}"))
    nfo = ep_dir / f"{show_title} - S{season:02d}E{ep_num:02d} - {safe_title}.nfo"
    if nfo.exists():
        return
    plot = enhance_plot(ep_data.get("name", ""), ep_data.get("overview", ""), config, log_func)
    root = Element("episodedetails")
    SubElement(root, "title").text = ep_data.get("name", "")
    SubElement(root, "plot").text = plot
    SubElement(root, "aired").text = ep_data.get("air_date", "")
    SubElement(root, "season").text = str(season)
    SubElement(root, "episode").text = str(ep_num)
    SubElement(root, "rating").text = str(ep_data.get("vote_average", "0"))
    SubElement(root, "uniqueid", type="tmdb", default="true").text = f"{tv_id}/{season}/{ep_num}"
    with open(nfo, 'w', encoding='utf-8') as f:
        f.write(minidom.parseString(tostring(root, 'utf-8')).toprettyxml(indent="  "))

# ==================== 硬链接（支持跨设备回退为软链接） ====================
def create_link(src: Path, dst: Path, link_type: str, log_func=None) -> bool:
    if dst.exists():
        try:
            if os.path.samefile(src, dst):
                if log_func:
                    log_func(f"🔗 链接已存在: {dst.name}", LOG_INFO)
                return True
        except:
            pass
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        if link_type == "symlink":
            os.symlink(src, dst)
        else:
            os.link(get_long_path(src), get_long_path(dst))
        if log_func:
            log_func(f"✅ 链接创建成功", LOG_SUCCESS)
        return True
    except OSError as e:
        if e.errno == 18:  # Invalid cross-device link
            if log_func:
                log_func(f"⚠️ 跨设备，改用软链接: {e}", LOG_WARNING)
            try:
                os.symlink(src, dst)
                if log_func:
                    log_func(f"✅ 软链接创建成功", LOG_SUCCESS)
                return True
            except Exception as e2:
                if log_func:
                    log_func(f"❌ 软链接也失败: {e2}", LOG_ERROR)
                return False
        else:
            if log_func:
                log_func(f"❌ 链接创建失败: {e}", LOG_ERROR)
            return False

# ==================== 处理单个文件（支持停止标志） ====================
def process_video(src: Path, config: dict, cache_dict: Dict[str, dict], log_func=None) -> bool:
    # 检查停止标志
    if stop_processing.is_set():
        if log_func:
            log_func(f"⏹️ 收到停止信号，跳过: {src.name}", LOG_WARNING)
        return False

    try:
        info = parse_filename(src.name, config, log_func)
        media_type = info.get("media_type")
        title = info.get("title")
        year = info.get("year")
        year_guess = info.get("year_guess")
        alt_titles = info.get("alternative_titles", [])

        if not title or media_type not in ("movie", "tv"):
            if log_func:
                log_func(f"❌ 无法识别媒体类型: {src.name}", LOG_ERROR)
            return False

        # 确定搜索年份：优先使用文件名中的年份，其次 AI 推测年份
        search_year = year if year and year != "null" else (year_guess if year_guess else None)
        year_str = search_year if search_year else "未知"
        if log_func:
            if media_type == "movie":
                log_func(f"🎬 识别为电影: {title} ({year_str})", LOG_SUCCESS)
            else:
                log_func(f"📺 识别为剧集: {title} S{info['season']:02d}E{info['episode']:02d}", LOG_SUCCESS)

        # 搜索 TMDB（传入别名）
        tmdb_result = search_tmdb(media_type, title, search_year, config, log_func, alt_titles=alt_titles)
        if not tmdb_result:
            return False

        tmdb_id = tmdb_result["id"]
        official_title = tmdb_result.get("title" if media_type == "movie" else "name", title)
        release_date = tmdb_result.get("release_date" if media_type == "movie" else "first_air_date", "")
        official_year = release_date[:4] if release_date else search_year

        details = get_tmdb_details(media_type, tmdb_id, config, log_func)
        if not details:
            return False

        if media_type == "movie":
            # 处理电影
            safe_title = sanitize_filename(official_title)
            folder_name = f"{safe_title} ({official_year})" if config.get("add_year_to_folder") and official_year else safe_title
            target_root = Path(config["movie_target_folder"])
            movie_dir = target_root / folder_name

            write_movie_nfo(movie_dir, official_title, tmdb_id, details.get("overview", ""), official_year, config, log_func)
            if config.get("download_images"):
                if poster := details.get("poster_path"):
                    download_image(config["image_base_url"] + poster, movie_dir / "poster.jpg", log_func)
                if backdrop := details.get("backdrop_path"):
                    download_image(config["image_base_url"] + backdrop, movie_dir / "fanart.jpg", log_func)

            target_path = movie_dir / f"{folder_name}{src.suffix}"
            if config.get("dry_run"):
                if log_func: log_func(f"🔍 [模拟] -> {target_path}", LOG_INFO)
                return True

            if not create_link(src, target_path, config["link_type"], log_func):
                return False

            src_str = str(src.resolve())
            with cache_lock:
                cache_dict[src_str] = {
                    "target": str(target_path.resolve()),
                    "fingerprint": get_file_fingerprint(src),
                    "media_type": "movie",
                    "title": official_title,
                    "year": official_year
                }
            if log_func: log_func(f"💾 缓存已写入", LOG_SUCCESS)
            return True

        else:
            # 处理剧集
            season = info["season"]
            episode = info["episode"]
            if season is None or episode is None:
                if log_func: log_func(f"❌ 剧集缺少季/集信息: {src.name}", LOG_ERROR)
                return False

            # ========== 增强的自动修正（支持跨季） ==========
            seasons_info = details.get("seasons", [])
            if seasons_info:
                # 过滤掉第零季（特典、花絮等）
                seasons_info = [s for s in seasons_info if s.get("season_number", 0) > 0]
                if seasons_info:
                    seasons_info.sort(key=lambda x: x["season_number"])

                    # 构建累计集数映射
                    cumulative = {}
                    total = 0
                    for s in seasons_info:
                        sn = s["season_number"]
                        ec = s.get("episode_count", 0)
                        total += ec
                        cumulative[sn] = total

                    current_season = season
                    current_episode = episode
                    max_ep_current = next((s.get("episode_count", 0) for s in seasons_info if s["season_number"] == current_season), 0)

                    # 如果 episode 超过当前季最大集数，尝试向后查找
                    if current_episode > max_ep_current:
                        target_season = None
                        target_episode = None
                        for sn in sorted(cumulative.keys()):
                            if cumulative[sn] >= current_episode:
                                target_season = sn
                                prev_total = cumulative.get(sn - 1, 0) if sn > 1 else 0
                                target_episode = current_episode - prev_total
                                break

                        if target_season is not None and target_season != current_season:
                            # 跨季修正
                            if log_func:
                                log_func(f"🔧 跨季修正: S{current_season:02d}E{current_episode:02d} -> S{target_season:02d}E{target_episode:02d}", LOG_WARNING)
                            season = target_season
                            episode = target_episode
                        elif target_season == current_season:
                            # 同一季内的全局编号修正
                            prev_total = cumulative.get(current_season - 1, 0) if current_season > 1 else 0
                            corrected_ep = current_episode - prev_total
                            if 1 <= corrected_ep <= max_ep_current:
                                if log_func:
                                    log_func(f"🔧 同季修正: S{current_season:02d}E{current_episode:02d} -> S{current_season:02d}E{corrected_ep:02d} (全局编号)", LOG_WARNING)
                                episode = corrected_ep
                    else:
                        # episode 在当前季正常范围内，不做修正
                        pass
            # =================================================

            # 获取该季的剧集列表
            episodes = get_tv_season_episodes(tmdb_id, season, config, log_func)
            ep_data = next((ep for ep in episodes if ep.get("episode_number") == episode), None)
            if not ep_data:
                # 增强错误提示：显示该季可用的集号
                available_eps = [ep.get("episode_number") for ep in episodes if ep.get("episode_number")]
                available_eps_str = str(sorted(available_eps)) if available_eps else "无数据"
                if log_func:
                    log_func(f"❌ TMDB 中无 S{season:02d}E{episode:02d} 数据。该季共有 {len(episodes)} 集，编号: {available_eps_str}", LOG_ERROR)
                return False

            safe_title = sanitize_filename(official_title)
            folder_name = f"{safe_title} ({official_year})" if config.get("add_year_to_folder") and official_year else safe_title
            target_root = Path(config["tv_target_folder"])
            show_dir = target_root / folder_name
            season_dir = show_dir / f"Season {season:02d}"

            write_tvshow_nfo(show_dir, official_title, tmdb_id, details.get("overview", ""), official_year, len(details.get("seasons", [])), config, log_func)
            if config.get("download_images"):
                if poster := details.get("poster_path"):
                    download_image(config["image_base_url"] + poster, show_dir / "poster.jpg", log_func)
                if backdrop := details.get("backdrop_path"):
                    download_image(config["image_base_url"] + backdrop, show_dir / "fanart.jpg", log_func)
            write_season_nfo(season_dir, season, tmdb_id, log_func)
            if still := ep_data.get("still_path"):
                if config.get("download_images"):
                    img_name = f"{safe_title} - S{season:02d}E{episode:02d} - {sanitize_filename(ep_data.get('name', ''))}.jpg"
                    download_image(config["image_base_url"] + still, season_dir / img_name, log_func)
            write_episode_nfo(season_dir, ep_data, safe_title, season, episode, tmdb_id, config, log_func)

            ep_title_clean = sanitize_filename(ep_data.get("name", ""))
            target_name = f"{folder_name} - S{season:02d}E{episode:02d}"
            if ep_title_clean:
                target_name += f" - {ep_title_clean}"
            target_path = season_dir / (target_name + src.suffix)

            if config.get("dry_run"):
                if log_func: log_func(f"🔍 [模拟] -> {target_path}", LOG_INFO)
                return True

            if not create_link(src, target_path, config["link_type"], log_func):
                return False

            src_str = str(src.resolve())
            with cache_lock:
                cache_dict[src_str] = {
                    "target": str(target_path.resolve()),
                    "fingerprint": get_file_fingerprint(src),
                    "media_type": "tv",
                    "title": official_title,
                    "season": season,
                    "episode": episode
                }
            if log_func: log_func(f"💾 缓存已写入", LOG_SUCCESS)
            return True

    except Exception as e:
        logging.error(f"异常 {src}: {e}")
        if log_func: log_func(f"❌ 处理异常: {e}", LOG_ERROR)
        return False
# ==================== 主流程（支持停止标志） ====================
def run_processor_with_callback(config_path: str, progress_callback=None):
    global stop_processing
    stop_processing.clear()  # 重置停止标志

    config = load_config(config_path)
    cache = load_cache() if config.get("incremental") else {}
    new_cache = {}

    def log_func(msg, level=LOG_INFO):
        if progress_callback:
            progress_callback(0, 0, msg, level)

    video_files = []
    for folder in config["source_folders"]:
        p = Path(folder)
        if p.exists():
            for f in p.rglob("*"):
                if f.is_file() and is_video_file(f, config):
                    video_files.append(f)

    total_files = len(video_files)
    log_func(f"🔍 扫描完成，共 {total_files} 个视频文件", LOG_SUCCESS)

    to_process = []
    for src in video_files:
        src_str = str(src.resolve())
        if config.get("incremental") and src_str in cache:
            if is_already_processed(src, cache[src_str], config):
                with cache_lock:
                    new_cache[src_str] = cache[src_str]
                continue
        to_process.append(src)

    total = len(to_process)
    log_func(f"📝 待处理 {total} 个文件", LOG_INFO)

    success = 0
    with ThreadPoolExecutor(max_workers=config.get("max_workers", 3)) as executor:
        futures = {executor.submit(process_video, src, config, new_cache, log_func): src for src in to_process}
        for i, future in enumerate(as_completed(futures), 1):
            if stop_processing.is_set():
                for f in futures:
                    f.cancel()
                log_func("⏹️ 任务已停止", LOG_WARNING)
                break
            try:
                if future.result():
                    success += 1
            except Exception as e:
                log_func(f"任务异常: {e}", LOG_ERROR)
            if progress_callback:
                progress_callback(i, total, f"进度 {i}/{total}", LOG_PROGRESS)

    if config.get("incremental") and not config.get("dry_run") and not stop_processing.is_set():
        save_cache(new_cache)
        log_func(f"💾 缓存已保存，共 {len(new_cache)} 条", LOG_SUCCESS)
    elif stop_processing.is_set():
        log_func("⚠️ 任务被中断，未保存缓存", LOG_WARNING)

    log_func(f"🎉 全部完成！成功处理 {success}/{total} 个文件", LOG_SUCCESS)

def stop_processing_task():
    """停止当前运行的任务"""
    stop_processing.set()

def reset_stop_flag():
    """重置停止标志（新任务开始前调用）"""
    stop_processing.clear()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=CONFIG_FILE)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force-full", action="store_true")
    args = parser.parse_args()
    config = load_config(args.config)
    if args.dry_run:
        config["dry_run"] = True
    if args.force_full:
        config["incremental"] = False

    def console_log(cur, tot, msg, level):
        print(f"[{level.upper()}] {msg}")

    run_processor_with_callback(args.config, console_log)

if __name__ == "__main__":
    main()
