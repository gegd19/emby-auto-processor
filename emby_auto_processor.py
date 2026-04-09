#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Emby 全自动入库工具 v4.0 最终全能版
- 支持电影和剧集智能识别
- 电影 → 调用 TMDB Movie API，放入独立电影目录
- 剧集 → 调用 TMDB TV API，放入剧集目录
- AI 解析增强 + 详细日志 + 增量缓存 + Web 界面支持
- 导出 create_retry_session 供 Web 流式路由使用
"""
#
# import os
# import re
# import json
# import time
# import hashlib
# import argparse
# import platform
# import logging
# import threading
# import requests
# from pathlib import Path
# from typing import List, Optional, Tuple, Dict, Any
# from concurrent.futures import ThreadPoolExecutor, as_completed
# from requests.adapters import HTTPAdapter
# from urllib3.util.retry import Retry
# from xml.etree.ElementTree import Element, SubElement, tostring
# from xml.dom import minidom
#
# logging.basicConfig(
#     filename="auto_processor_errors.log",
#     level=logging.ERROR,
#     format="%(asctime)s - %(levelname)s - %(message)s"
# )
#
# CONFIG_FILE = "auto_config.json"
# CACHE_FILE = "auto_processed_cache.json"
#
# DEFAULT_CONFIG = {
#     "source_folders": ["D:/moive"],
#     "tv_target_folder": "D:/Emby_Media/TV Shows",
#     "movie_target_folder": "D:/Emby_Media/Movies",
#     "video_extensions": [".mkv", ".mp4", ".avi", ".ts", ".m2ts", ".mov", ".wmv", ".flv"],
#     "link_type": "hard",
#     "ignore_patterns": ["sample", "trailer", "extra"],
#     "min_file_size_mb": 0,
#     "dry_run": False,
#     "add_year_to_folder": True,
#     "force_chinese_name": True,
#     "incremental": True,
#     "max_workers": 3,
#     "download_images": True,
#     "image_base_url": "https://image.tmdb.org/t/p/original",
#     "tmdb_api": {"api_key": "YOUR_TMDB_API_KEY_V3", "language": "zh-CN"},
#     "ai_parser": {
#         "enabled": False,
#         "provider": "deepseek",
#         "api_key": "YOUR_API_KEY",
#         "model": "deepseek-chat",
#         "base_url": "https://api.deepseek.com",
#         "temperature": 0.1,
#         "max_tokens": 300,
#         "timeout": 20
#     },
#     "ai_plot_enhance": {
#         "enabled": False,
#         "provider": "deepseek",
#         "api_key": "YOUR_API_KEY",
#         "model": "deepseek-chat",
#         "base_url": "https://api.deepseek.com",
#         "temperature": 0.7,
#         "max_tokens": 500,
#         "timeout": 30,
#         "prompt_template": "你是一个专业的影视剧文案。请将以下剧情简介改写得更加生动、吸引人，语言流畅自然，可以适当增加一些悬念和感染力。请直接输出改写后的简介，不要添加额外说明。\n\n原标题：{title}\n原简介：{original_plot}\n\n优化后简介："
#     }
# }
#
# cache_lock = threading.Lock()
#
# LOG_INFO = "info"
# LOG_SUCCESS = "success"
# LOG_ERROR = "error"
# LOG_WARNING = "warning"
# LOG_PROGRESS = "progress"
#
# # ==================== 配置与缓存 ====================
# def load_config(config_path: str = CONFIG_FILE) -> dict:
#     if os.path.exists(config_path):
#         with open(config_path, 'r', encoding='utf-8') as f:
#             user_config = json.load(f)
#             merged = DEFAULT_CONFIG.copy()
#             for k, v in user_config.items():
#                 if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
#                     merged[k] = {**merged[k], **v}
#                 else:
#                     merged[k] = v
#             return merged
#     else:
#         with open(config_path, 'w', encoding='utf-8') as f:
#             json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
#         return DEFAULT_CONFIG
#
# def load_cache() -> Dict[str, dict]:
#     if os.path.exists(CACHE_FILE):
#         try:
#             with open(CACHE_FILE, 'r', encoding='utf-8') as f:
#                 return json.load(f)
#         except:
#             return {}
#     return {}
#
# def save_cache(cache: Dict[str, dict]):
#     with cache_lock:
#         with open(CACHE_FILE, 'w', encoding='utf-8') as f:
#             json.dump(cache, f, ensure_ascii=False, indent=2)
#
# def get_file_fingerprint(filepath: Path) -> str:
#     stat = filepath.stat()
#     raw = f"{str(filepath.resolve())}|{stat.st_size}|{stat.st_mtime}"
#     return hashlib.md5(raw.encode()).hexdigest()
#
# def is_already_processed(src: Path, cache_entry: dict, config: dict, log_func=None) -> bool:
#     target = Path(cache_entry.get("target", ""))
#     if not target.exists():
#         return False
#     current_fp = get_file_fingerprint(src)
#     if cache_entry.get("fingerprint") != current_fp:
#         return False
#     try:
#         if config["link_type"] == "hard":
#             return os.path.samefile(src, target)
#         else:
#             return target.resolve() == src.resolve()
#     except:
#         return False
#
# # ==================== 工具函数 ====================
# def get_long_path(path: Path) -> str:
#     if platform.system() == "Windows":
#         abs_path = str(path.resolve())
#         if not abs_path.startswith("\\\\?\\"):
#             return "\\\\?\\" + abs_path
#         return abs_path
#     return str(path)
#
# def sanitize_filename(name: str) -> str:
#     if not name:
#         return "Unknown"
#     return re.sub(r'[\\/*?:"<>|]', '_', name).strip()
#
# def is_video_file(filepath: Path, config: dict) -> bool:
#     ext = filepath.suffix.lower()
#     allowed = [e.lower() for e in config["video_extensions"]]
#     if ext not in allowed:
#         return False
#     name_lower = filepath.stem.lower()
#     for pattern in config["ignore_patterns"]:
#         if re.search(rf'\b{re.escape(pattern.lower())}\b', name_lower):
#             return False
#     min_mb = config.get("min_file_size_mb", 0)
#     if min_mb > 0:
#         try:
#             if filepath.stat().st_size / (1024 * 1024) < min_mb:
#                 return False
#         except:
#             return False
#     return True
#
# def create_retry_session() -> requests.Session:
#     session = requests.Session()
#     retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
#     session.mount('https://', HTTPAdapter(max_retries=retries))
#     return session
#
# # ==================== AI 调用 ====================
# def call_ai_api(prompt: str, ai_config: dict, log_func=None) -> Optional[str]:
#     provider = ai_config.get("provider", "deepseek")
#     api_key = ai_config.get("api_key")
#     model = ai_config.get("model")
#     base_url = ai_config.get("base_url", "https://api.deepseek.com")
#     temperature = ai_config.get("temperature", 0.7)
#     max_tokens = ai_config.get("max_tokens", 500)
#     timeout = ai_config.get("timeout", 30)
#
#     url_map = {
#         "deepseek": f"{base_url}/v1/chat/completions",
#         "openai": "https://api.openai.com/v1/chat/completions",
#         "zhipu": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
#         "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
#     }
#     url = url_map.get(provider)
#     if not url:
#         if log_func:
#             log_func(f"❌ 不支持的 AI 提供商: {provider}", LOG_ERROR)
#         return None
#
#     if log_func:
#         log_func(f"🤖 调用 AI API: {provider} 模型 {model}", LOG_INFO)
#
#     headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
#     payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": temperature, "max_tokens": max_tokens}
#     session = create_retry_session()
#     try:
#         start = time.time()
#         resp = session.post(url, headers=headers, json=payload, timeout=timeout)
#         resp.raise_for_status()
#         elapsed = time.time() - start
#         if log_func:
#             log_func(f"✅ AI 响应成功 ({elapsed:.2f}s)", LOG_SUCCESS)
#         return resp.json()['choices'][0]['message']['content'].strip()
#     except Exception as e:
#         if log_func:
#             log_func(f"❌ AI API 调用失败: {e}", LOG_ERROR)
#         return None
#
# # ==================== AI 智能解析（支持电影/剧集识别） ====================
# AI_CACHE = {}
#
# def parse_filename_with_ai(filename: str, config: dict, log_func=None) -> dict:
#     ai_cfg = config.get("ai_parser", {})
#     if log_func:
#         log_func(f"🤖 AI 解析文件名: {filename[:50]}...", LOG_INFO)
#
#     force_chinese = config.get("force_chinese_name", True)
#     prompt = f"""
# 分析以下视频文件名，返回 JSON：
# 文件名：{filename}
#
# 请判断这是电影还是剧集，并提取以下信息：
# - media_type: "movie" 或 "tv"
# - title: 影视名称({'必须为中文' if force_chinese else '原始名称'})
# - year: 发行年份（四位数字，若无则为 null）
# - season: 季号（仅剧集，电影为 null）
# - episode: 集号（仅剧集，电影为 null）
# - episode_title: 单集标题（若无则为空字符串）
#
# 注意：
# - 若文件名无明显季集标识（如 S01E01、第1季），应判定为电影。
# - 忽略压制组、分辨率等技术标签。
# - 只返回合法 JSON，不要任何解释。
#
# 返回示例（剧集）：
# {{"media_type": "tv", "title": "龙族", "year": 2025, "season": 2, "episode": 5, "episode_title": ""}}
#
# 返回示例（电影）：
# {{"media_type": "movie", "title": "哪吒之魔童闹海", "year": 2025, "season": null, "episode": null, "episode_title": ""}}
# """
#     resp = call_ai_api(prompt, ai_cfg, log_func)
#     if not resp:
#         return {"media_type": "unknown"}
#
#     try:
#         start = resp.find('{')
#         end = resp.rfind('}')
#         json_str = resp[start:end+1] if (start != -1 and end != -1) else resp.strip().strip('`').strip('json')
#         data = json.loads(json_str)
#         return data
#     except Exception as e:
#         if log_func:
#             log_func(f"❌ AI 响应解析失败: {e}", LOG_ERROR)
#         return {"media_type": "unknown"}
#
# def parse_filename_regex(filename: str) -> dict:
#     name = Path(filename).stem
#     name = re.sub(r'\.\.\w+$', '', name)
#     name = re.sub(r'^\[[^\]]+\]\s*', '', name)
#     year = re.search(r'\b(19|20)\d{2}\b', name)
#     year = year.group(0) if year else None
#
#     # 检测季集标识
#     tv_patterns = [
#         r'[Ss](\d{1,2})[Ee](\d{1,2})',
#         r'(\d{1,2})[xX](\d{1,2})',
#         r'第\s*(\d{1,2})\s*季\s*第\s*(\d{1,2})\s*集',
#         r'\[(\d{1,2})\]'
#     ]
#     season, episode = None, None
#     for p in tv_patterns:
#         m = re.search(p, name, re.I)
#         if m:
#             if p in [r'[Ss](\d{1,2})[Ee](\d{1,2})', r'(\d{1,2})[xX](\d{1,2})', r'第\s*(\d{1,2})\s*季\s*第\s*(\d{1,2})\s*集']:
#                 season, episode = int(m.group(1)), int(m.group(2))
#             else:
#                 season, episode = 1, int(m.group(1))
#             break
#
#     media_type = "tv" if episode is not None else "movie"
#
#     # 清理名称
#     name = re.sub(r'[\[\]\(\)【】_,\.-]', ' ', name)
#     name = re.sub(r'\b(1080p|720p|4K|HDR|HEVC|x264|x265|AAC|WEB-DL|BluRay)\b', '', name, flags=re.I)
#     name = re.sub(r'\s+', ' ', name).strip()
#     title = name.split(' ')[0] if name else Path(filename).stem.split('.')[0]
#     if not re.search(r'[\u4e00-\u9fff]', title):
#         eng = re.search(r'[A-Za-z0-9!]+(?:\s+[A-Za-z0-9!]+)*', title)
#         if eng:
#             title = eng.group(0)
#
#     return {
#         "media_type": media_type,
#         "title": title,
#         "year": year,
#         "season": season,
#         "episode": episode,
#         "episode_title": ""
#     }
#
# def parse_filename(filename: str, config: dict, log_func=None) -> dict:
#     if filename in AI_CACHE:
#         return AI_CACHE[filename]
#     if config.get("ai_parser", {}).get("enabled"):
#         res = parse_filename_with_ai(filename, config, log_func)
#         if res.get("media_type") not in ("unknown", None):
#             AI_CACHE[filename] = res
#             return res
#     res = parse_filename_regex(filename)
#     AI_CACHE[filename] = res
#     return res
#
# # ==================== AI 英文翻译 ====================
# def get_english_name_from_ai(chinese_name: str, config: dict, log_func=None):
#     if not config.get("ai_parser", {}).get("enabled"):
#         return None
#     if log_func:
#         log_func(f"🤖 请求 AI 翻译英文名: {chinese_name}", LOG_INFO)
#     resp = call_ai_api(f"请将以下中文影视名称翻译为英文原名，只返回英文名：{chinese_name}", config["ai_parser"], log_func)
#     if not resp:
#         return None
#     cleaned = re.sub(r'^(Original English Title|英文原名|English Name)[:\s]*', '', resp, flags=re.IGNORECASE).strip()
#     return cleaned if cleaned else resp.strip()
#
# # ==================== AI 简介美化 ====================
# PLOT_CACHE = {}
#
# def enhance_plot(title: str, original_plot: str, config: dict, log_func=None) -> str:
#     if not original_plot or original_plot == "暂无简介":
#         return original_plot
#     key = f"{title}|{original_plot}"
#     if key in PLOT_CACHE:
#         return PLOT_CACHE[key]
#     if not config.get("ai_plot_enhance", {}).get("enabled"):
#         return original_plot
#     if log_func:
#         log_func(f"🤖 AI 改写简介: {title}", LOG_INFO)
#     prompt = config["ai_plot_enhance"]["prompt_template"].format(title=title, original_plot=original_plot)
#     start = time.time()
#     enhanced = call_ai_api(prompt, config["ai_plot_enhance"], log_func)
#     if enhanced:
#         PLOT_CACHE[key] = enhanced
#         if log_func:
#             log_func(f"✅ 简介改写完成 ({time.time()-start:.2f}s)", LOG_SUCCESS)
#         return enhanced
#     return original_plot
#
# # ==================== TMDB 搜索 ====================
# def search_tmdb(media_type: str, query: str, year: Optional[str], config: dict, log_func=None) -> Optional[Dict]:
#     api_key = config["tmdb_api"]["api_key"]
#     lang = config["tmdb_api"].get("language", "zh-CN")
#     url = f"https://api.themoviedb.org/3/search/{media_type}"
#
#     def _search(q, y):
#         params = {"api_key": api_key, "query": q, "language": lang}
#         if y:
#             params["primary_release_year" if media_type == "movie" else "first_air_date_year"] = y
#         if log_func:
#             log_func(f"🌐 TMDB {media_type.upper()}: GET {url}?query={q}&year={y}", LOG_INFO)
#         try:
#             resp = requests.get(url, params=params, timeout=15)
#             resp.raise_for_status()
#             results = resp.json().get("results", [])
#             if results:
#                 return results[0]
#         except:
#             pass
#         return None
#
#     # 1. 原词 + 年份
#     for q in [query, re.sub(r'[！!？?\-—]', '', query)]:
#         r = _search(q, year)
#         if r:
#             return r
#
#     # 2. 原词不带年份
#     r = _search(query, None)
#     if r:
#         return r
#
#     # 3. 英文名尝试
#     if re.search(r'[\u4e00-\u9fff]', query):
#         eng = get_english_name_from_ai(query, config, log_func)
#         if eng:
#             for q in [eng, re.sub(r'[-:].*$', '', eng).strip()]:
#                 r = _search(q, year)
#                 if r:
#                     return r
#
#     if log_func:
#         log_func(f"❌ TMDB 搜索无结果: {query}", LOG_ERROR)
#     return None
#
# def get_tmdb_details(media_type: str, tmdb_id: int, config: dict, log_func=None):
#     url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}"
#     params = {"api_key": config["tmdb_api"]["api_key"], "language": config["tmdb_api"].get("language", "zh-CN")}
#     if log_func:
#         log_func(f"🌐 获取详情: GET {url}", LOG_INFO)
#     try:
#         return requests.get(url, params=params, timeout=15).json()
#     except:
#         return None
#
# def get_tv_season_episodes(tv_id: int, season_num: int, config: dict, log_func=None):
#     url = f"https://api.themoviedb.org/3/tv/{tv_id}/season/{season_num}"
#     params = {"api_key": config["tmdb_api"]["api_key"], "language": config["tmdb_api"].get("language", "zh-CN")}
#     try:
#         return requests.get(url, params=params, timeout=15).json().get("episodes", [])
#     except:
#         return []
#
# # ==================== 图片下载 ====================
# def download_image(url: str, save_path: Path, log_func=None) -> bool:
#     if save_path.exists():
#         return True
#     try:
#         save_path.parent.mkdir(parents=True, exist_ok=True)
#         if log_func:
#             log_func(f"⬇️ 下载图片: {save_path.name}", LOG_INFO)
#         resp = requests.get(url, timeout=30)
#         resp.raise_for_status()
#         with open(save_path, 'wb') as f:
#             f.write(resp.content)
#         if log_func:
#             log_func(f"✅ 图片下载完成", LOG_SUCCESS)
#         return True
#     except Exception as e:
#         if log_func:
#             log_func(f"❌ 图片下载失败: {e}", LOG_ERROR)
#         return False
#
# # ==================== NFO 生成 ====================
# def write_movie_nfo(movie_dir: Path, title: str, tmdb_id: int, overview: str, year: str, config: dict, log_func=None):
#     movie_dir.mkdir(parents=True, exist_ok=True)
#     nfo = movie_dir / "movie.nfo"
#     if nfo.exists():
#         return
#     if config.get("ai_plot_enhance", {}).get("enabled"):
#         overview = enhance_plot(title, overview, config, log_func)
#     root = Element("movie")
#     SubElement(root, "title").text = title
#     SubElement(root, "plot").text = overview or ""
#     if year and year != "0000":
#         SubElement(root, "year").text = year
#     SubElement(root, "uniqueid", type="tmdb", default="true").text = str(tmdb_id)
#     with open(nfo, 'w', encoding='utf-8') as f:
#         f.write(minidom.parseString(tostring(root, 'utf-8')).toprettyxml(indent="  "))
#     if log_func:
#         log_func(f"📄 写入 movie.nfo", LOG_INFO)
#
# def write_tvshow_nfo(show_dir: Path, title: str, tmdb_id: int, overview: str, year: str, num_seasons: int, config: dict, log_func=None):
#     show_dir.mkdir(parents=True, exist_ok=True)
#     nfo = show_dir / "tvshow.nfo"
#     if nfo.exists():
#         return
#     if config.get("ai_plot_enhance", {}).get("enabled"):
#         overview = enhance_plot(title, overview, config, log_func)
#     root = Element("tvshow")
#     SubElement(root, "title").text = title
#     SubElement(root, "plot").text = overview or ""
#     if year and year != "0000":
#         SubElement(root, "premiered").text = f"{year}-01-01"
#     SubElement(root, "uniqueid", type="tmdb", default="true").text = str(tmdb_id)
#     SubElement(root, "numseasons").text = str(num_seasons)
#     with open(nfo, 'w', encoding='utf-8') as f:
#         f.write(minidom.parseString(tostring(root, 'utf-8')).toprettyxml(indent="  "))
#     if log_func:
#         log_func(f"📄 写入 tvshow.nfo", LOG_INFO)
#
# def write_season_nfo(season_dir: Path, season_num: int, tv_id: int, log_func=None):
#     season_dir.mkdir(parents=True, exist_ok=True)
#     nfo = season_dir / "season.nfo"
#     if nfo.exists():
#         return
#     root = Element("season")
#     SubElement(root, "seasonnumber").text = str(season_num)
#     SubElement(root, "uniqueid", type="tmdb", default="true").text = f"{tv_id}/{season_num}"
#     with open(nfo, 'w', encoding='utf-8') as f:
#         f.write(minidom.parseString(tostring(root, 'utf-8')).toprettyxml(indent="  "))
#
# def write_episode_nfo(ep_dir: Path, ep_data: dict, show_title: str, season: int, ep_num: int, tv_id: int, config: dict, log_func=None):
#     ep_dir.mkdir(parents=True, exist_ok=True)
#     safe_title = sanitize_filename(ep_data.get("name", f"Episode {ep_num}"))
#     nfo = ep_dir / f"{show_title} - S{season:02d}E{ep_num:02d} - {safe_title}.nfo"
#     if nfo.exists():
#         return
#     plot = enhance_plot(ep_data.get("name", ""), ep_data.get("overview", ""), config, log_func)
#     root = Element("episodedetails")
#     SubElement(root, "title").text = ep_data.get("name", "")
#     SubElement(root, "plot").text = plot
#     SubElement(root, "aired").text = ep_data.get("air_date", "")
#     SubElement(root, "season").text = str(season)
#     SubElement(root, "episode").text = str(ep_num)
#     SubElement(root, "rating").text = str(ep_data.get("vote_average", "0"))
#     SubElement(root, "uniqueid", type="tmdb", default="true").text = f"{tv_id}/{season}/{ep_num}"
#     with open(nfo, 'w', encoding='utf-8') as f:
#         f.write(minidom.parseString(tostring(root, 'utf-8')).toprettyxml(indent="  "))
#
# # ==================== 硬链接 ====================
# def create_link(src: Path, dst: Path, link_type: str, log_func=None) -> bool:
#     if dst.exists():
#         try:
#             if os.path.samefile(src, dst):
#                 if log_func:
#                     log_func(f"🔗 硬链接已存在: {dst.name}", LOG_INFO)
#                 return True
#         except:
#             pass
#         return False
#     dst.parent.mkdir(parents=True, exist_ok=True)
#     try:
#         if link_type == "symlink":
#             os.symlink(src, dst)
#         else:
#             os.link(get_long_path(src), get_long_path(dst))
#         if log_func:
#             log_func(f"✅ 硬链接创建成功", LOG_SUCCESS)
#         return True
#     except OSError as e:
#         if log_func:
#             log_func(f"❌ 硬链接创建失败: {e}", LOG_ERROR)
#         return False
#
# # ==================== 处理单个文件 ====================
# def process_video(src: Path, config: dict, cache_dict: Dict[str, dict], log_func=None) -> bool:
#     try:
#         info = parse_filename(src.name, config, log_func)
#         media_type = info.get("media_type")
#         title = info.get("title")
#         year = info.get("year")
#         if not title or media_type not in ("movie", "tv"):
#             if log_func:
#                 log_func(f"❌ 无法识别媒体类型: {src.name}", LOG_ERROR)
#             return False
#
#         year_str = year if year else "未知"
#         if log_func:
#             if media_type == "movie":
#                 log_func(f"🎬 识别为电影: {title} ({year_str})", LOG_SUCCESS)
#             else:
#                 log_func(f"📺 识别为剧集: {title} S{info['season']:02d}E{info['episode']:02d}", LOG_SUCCESS)
#
#         # 搜索 TMDB
#         tmdb_result = search_tmdb(media_type, title, year, config, log_func)
#         if not tmdb_result:
#             return False
#
#         tmdb_id = tmdb_result["id"]
#         official_title = tmdb_result.get("title" if media_type == "movie" else "name", title)
#         release_date = tmdb_result.get("release_date" if media_type == "movie" else "first_air_date", "")
#         official_year = release_date[:4] if release_date else year
#
#         details = get_tmdb_details(media_type, tmdb_id, config, log_func)
#         if not details:
#             return False
#
#         if media_type == "movie":
#             # 处理电影
#             safe_title = sanitize_filename(official_title)
#             folder_name = f"{safe_title} ({official_year})" if config.get("add_year_to_folder") and official_year else safe_title
#             target_root = Path(config["movie_target_folder"])
#             movie_dir = target_root / folder_name
#
#             write_movie_nfo(movie_dir, official_title, tmdb_id, details.get("overview", ""), official_year, config, log_func)
#             if config.get("download_images"):
#                 if poster := details.get("poster_path"):
#                     download_image(config["image_base_url"] + poster, movie_dir / "poster.jpg", log_func)
#                 if backdrop := details.get("backdrop_path"):
#                     download_image(config["image_base_url"] + backdrop, movie_dir / "fanart.jpg", log_func)
#
#             target_path = movie_dir / f"{folder_name}{src.suffix}"
#             if config.get("dry_run"):
#                 if log_func: log_func(f"🔍 [模拟] -> {target_path}", LOG_INFO)
#                 return True
#
#             if not create_link(src, target_path, config["link_type"], log_func):
#                 return False
#
#             src_str = str(src.resolve())
#             with cache_lock:
#                 cache_dict[src_str] = {
#                     "target": str(target_path.resolve()),
#                     "fingerprint": get_file_fingerprint(src),
#                     "media_type": "movie",
#                     "title": official_title,
#                     "year": official_year
#                 }
#             if log_func: log_func(f"💾 缓存已写入", LOG_SUCCESS)
#             return True
#
#         else:
#             # 处理剧集
#             season = info["season"]
#             episode = info["episode"]
#             episodes = get_tv_season_episodes(tmdb_id, season, config, log_func)
#             ep_data = next((ep for ep in episodes if ep.get("episode_number") == episode), None)
#             if not ep_data:
#                 if log_func: log_func(f"❌ TMDB 中无 S{season:02d}E{episode:02d} 数据", LOG_ERROR)
#                 return False
#
#             safe_title = sanitize_filename(official_title)
#             folder_name = f"{safe_title} ({official_year})" if config.get("add_year_to_folder") and official_year else safe_title
#             target_root = Path(config["tv_target_folder"])
#             show_dir = target_root / folder_name
#             season_dir = show_dir / f"Season {season:02d}"
#
#             write_tvshow_nfo(show_dir, official_title, tmdb_id, details.get("overview", ""), official_year, len(details.get("seasons", [])), config, log_func)
#             if config.get("download_images"):
#                 if poster := details.get("poster_path"):
#                     download_image(config["image_base_url"] + poster, show_dir / "poster.jpg", log_func)
#                 if backdrop := details.get("backdrop_path"):
#                     download_image(config["image_base_url"] + backdrop, show_dir / "fanart.jpg", log_func)
#             write_season_nfo(season_dir, season, tmdb_id, log_func)
#             if still := ep_data.get("still_path"):
#                 if config.get("download_images"):
#                     img_name = f"{safe_title} - S{season:02d}E{episode:02d} - {sanitize_filename(ep_data.get('name', ''))}.jpg"
#                     download_image(config["image_base_url"] + still, season_dir / "images" / img_name, log_func)
#             write_episode_nfo(season_dir, ep_data, safe_title, season, episode, tmdb_id, config, log_func)
#
#             ep_title_clean = sanitize_filename(ep_data.get("name", ""))
#             target_name = f"{folder_name} - S{season:02d}E{episode:02d}"
#             if ep_title_clean:
#                 target_name += f" - {ep_title_clean}"
#             target_path = season_dir / (target_name + src.suffix)
#
#             if config.get("dry_run"):
#                 if log_func: log_func(f"🔍 [模拟] -> {target_path}", LOG_INFO)
#                 return True
#
#             if not create_link(src, target_path, config["link_type"], log_func):
#                 return False
#
#             src_str = str(src.resolve())
#             with cache_lock:
#                 cache_dict[src_str] = {
#                     "target": str(target_path.resolve()),
#                     "fingerprint": get_file_fingerprint(src),
#                     "media_type": "tv",
#                     "title": official_title,
#                     "season": season,
#                     "episode": episode
#                 }
#             if log_func: log_func(f"💾 缓存已写入", LOG_SUCCESS)
#             return True
#
#     except Exception as e:
#         logging.error(f"异常 {src}: {e}")
#         if log_func: log_func(f"❌ 处理异常: {e}", LOG_ERROR)
#         return False
#
# # ==================== 主流程 ====================
# def run_processor_with_callback(config_path: str, progress_callback=None):
#     config = load_config(config_path)
#     cache = load_cache() if config.get("incremental") else {}
#     new_cache = {}
#
#     def log_func(msg, level=LOG_INFO):
#         if progress_callback:
#             progress_callback(0, 0, msg, level)
#
#     video_files = []
#     for folder in config["source_folders"]:
#         p = Path(folder)
#         if p.exists():
#             for f in p.rglob("*"):
#                 if f.is_file() and is_video_file(f, config):
#                     video_files.append(f)
#
#     total_files = len(video_files)
#     log_func(f"🔍 扫描完成，共 {total_files} 个视频文件", LOG_SUCCESS)
#
#     to_process = []
#     for src in video_files:
#         src_str = str(src.resolve())
#         if config.get("incremental") and src_str in cache:
#             if is_already_processed(src, cache[src_str], config):
#                 with cache_lock:
#                     new_cache[src_str] = cache[src_str]
#                 continue
#         to_process.append(src)
#
#     total = len(to_process)
#     log_func(f"📝 待处理 {total} 个文件", LOG_INFO)
#
#     success = 0
#     with ThreadPoolExecutor(max_workers=config.get("max_workers", 3)) as executor:
#         futures = {executor.submit(process_video, src, config, new_cache, log_func): src for src in to_process}
#         for i, future in enumerate(as_completed(futures), 1):
#             try:
#                 if future.result():
#                     success += 1
#             except:
#                 pass
#             if progress_callback:
#                 progress_callback(i, total, f"进度 {i}/{total}", LOG_PROGRESS)
#
#     if config.get("incremental") and not config.get("dry_run"):
#         save_cache(new_cache)
#         log_func(f"💾 缓存已保存，共 {len(new_cache)} 条", LOG_SUCCESS)
#
#     log_func(f"🎉 全部完成！成功处理 {success}/{total} 个文件", LOG_SUCCESS)
#
# def main():
#     parser = argparse.ArgumentParser()
#     parser.add_argument("--config", default=CONFIG_FILE)
#     parser.add_argument("--dry-run", action="store_true")
#     parser.add_argument("--force-full", action="store_true")
#     args = parser.parse_args()
#     config = load_config(args.config)
#     if args.dry_run:
#         config["dry_run"] = True
#     if args.force_full:
#         config["incremental"] = False
#
#     def console_log(cur, tot, msg, level):
#         print(f"[{level.upper()}] {msg}")
#
#     run_processor_with_callback(args.config, console_log)
#
# if __name__ == "__main__":
#     main()


#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Emby 全自动入库工具 v4.0 最终全能版
- 支持电影和剧集智能识别
- 电影 → 调用 TMDB Movie API，放入独立电影目录
- 剧集 → 调用 TMDB TV API，放入剧集目录
- AI 解析增强 + 详细日志 + 增量缓存 + Web 界面支持
- 导出 create_retry_session 供 Web 流式路由使用
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

logging.basicConfig(
    filename="auto_processor_errors.log",
    level=logging.ERROR,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

CONFIG_FILE = "auto_config.json"
CACHE_FILE = "auto_processed_cache.json"

DEFAULT_CONFIG = {
    "source_folders": ["D:/moive"],
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
        "max_tokens": 300,
        "timeout": 20
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

cache_lock = threading.Lock()

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
        return resp.json()['choices'][0]['message']['content'].strip()
    except Exception as e:
        if log_func:
            log_func(f"❌ AI API 调用失败: {e}", LOG_ERROR)
        return None

# ==================== AI 智能解析（支持电影/剧集识别） ====================
AI_CACHE = {}

def parse_filename_with_ai(filename: str, config: dict, log_func=None) -> dict:
    ai_cfg = config.get("ai_parser", {})
    if log_func:
        log_func(f"🤖 AI 解析文件名: {filename[:50]}...", LOG_INFO)

    force_chinese = config.get("force_chinese_name", True)
    prompt = f"""
分析以下视频文件名，返回 JSON：
文件名：{filename}

请判断这是电影还是剧集，并提取以下信息：
- media_type: "movie" 或 "tv"
- title: 影视名称({'必须为中文' if force_chinese else '原始名称'})
- year: 发行年份（四位数字，若无则为 null）
- season: 季号（仅剧集，电影为 null）
- episode: 集号（仅剧集，电影为 null）
- episode_title: 单集标题（若无则为空字符串）

注意：
- 若文件名无明显季集标识（如 S01E01、第1季），应判定为电影。
- 忽略压制组、分辨率等技术标签。
- 只返回合法 JSON，不要任何解释。

返回示例（剧集）：
{{"media_type": "tv", "title": "龙族", "year": 2025, "season": 2, "episode": 5, "episode_title": ""}}

返回示例（电影）：
{{"media_type": "movie", "title": "哪吒之魔童闹海", "year": 2025, "season": null, "episode": null, "episode_title": ""}}
"""
    resp = call_ai_api(prompt, ai_cfg, log_func)
    if not resp:
        return {"media_type": "unknown"}

    try:
        start = resp.find('{')
        end = resp.rfind('}')
        json_str = resp[start:end+1] if (start != -1 and end != -1) else resp.strip().strip('`').strip('json')
        data = json.loads(json_str)
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

    # 清理名称
    name = re.sub(r'[\[\]\(\)【】_,\.-]', ' ', name)
    name = re.sub(r'\b(1080p|720p|4K|HDR|HEVC|x264|x265|AAC|WEB-DL|BluRay)\b', '', name, flags=re.I)
    name = re.sub(r'\s+', ' ', name).strip()
    title = name.split(' ')[0] if name else Path(filename).stem.split('.')[0]
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
        "episode_title": ""
    }

def parse_filename(filename: str, config: dict, log_func=None) -> dict:
    if filename in AI_CACHE:
        return AI_CACHE[filename]
    if config.get("ai_parser", {}).get("enabled"):
        res = parse_filename_with_ai(filename, config, log_func)
        if res.get("media_type") not in ("unknown", None):
            AI_CACHE[filename] = res
            return res
    res = parse_filename_regex(filename)
    AI_CACHE[filename] = res
    return res

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

def enhance_plot(title: str, original_plot: str, config: dict, log_func=None) -> str:
    if not original_plot or original_plot == "暂无简介":
        return original_plot
    key = f"{title}|{original_plot}"
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
        PLOT_CACHE[key] = enhanced
        if log_func:
            log_func(f"✅ 简介改写完成 ({time.time()-start:.2f}s)", LOG_SUCCESS)
        return enhanced
    return original_plot

# ==================== TMDB 搜索 ====================
def search_tmdb(media_type: str, query: str, year: Optional[str], config: dict, log_func=None) -> Optional[Dict]:
    api_key = config["tmdb_api"]["api_key"]
    lang = config["tmdb_api"].get("language", "zh-CN")
    url = f"https://api.themoviedb.org/3/search/{media_type}"

    def _search(q, y):
        params = {"api_key": api_key, "query": q, "language": lang}
        if y:
            params["primary_release_year" if media_type == "movie" else "first_air_date_year"] = y
        if log_func:
            log_func(f"🌐 TMDB {media_type.upper()}: GET {url}?query={q}&year={y}", LOG_INFO)
        try:
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            results = resp.json().get("results", [])
            if results:
                return results[0]
        except:
            pass
        return None

    # 1. 原词 + 年份
    for q in [query, re.sub(r'[！!？?\-—]', '', query)]:
        r = _search(q, year)
        if r:
            return r

    # 2. 原词不带年份
    r = _search(query, None)
    if r:
        return r

    # 3. 英文名尝试
    if re.search(r'[\u4e00-\u9fff]', query):
        eng = get_english_name_from_ai(query, config, log_func)
        if eng:
            for q in [eng, re.sub(r'[-:].*$', '', eng).strip()]:
                r = _search(q, year)
                if r:
                    return r

    if log_func:
        log_func(f"❌ TMDB 搜索无结果: {query}", LOG_ERROR)
    return None

def get_tmdb_details(media_type: str, tmdb_id: int, config: dict, log_func=None):
    url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}"
    params = {"api_key": config["tmdb_api"]["api_key"], "language": config["tmdb_api"].get("language", "zh-CN")}
    if log_func:
        log_func(f"🌐 获取详情: GET {url}", LOG_INFO)
    try:
        return requests.get(url, params=params, timeout=15).json()
    except:
        return None

def get_tv_season_episodes(tv_id: int, season_num: int, config: dict, log_func=None):
    url = f"https://api.themoviedb.org/3/tv/{tv_id}/season/{season_num}"
    params = {"api_key": config["tmdb_api"]["api_key"], "language": config["tmdb_api"].get("language", "zh-CN")}
    try:
        return requests.get(url, params=params, timeout=15).json().get("episodes", [])
    except:
        return []

# ==================== 图片下载 ====================
def download_image(url: str, save_path: Path, log_func=None) -> bool:
    if save_path.exists():
        return True
    try:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        if log_func:
            log_func(f"⬇️ 下载图片: {save_path.name}", LOG_INFO)
        resp = requests.get(url, timeout=30)
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

# ==================== 硬链接 ====================
def create_link(src: Path, dst: Path, link_type: str, log_func=None) -> bool:
    if dst.exists():
        try:
            if os.path.samefile(src, dst):
                if log_func:
                    log_func(f"🔗 硬链接已存在: {dst.name}", LOG_INFO)
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
            log_func(f"✅ 硬链接创建成功", LOG_SUCCESS)
        return True
    except OSError as e:
        if log_func:
            log_func(f"❌ 硬链接创建失败: {e}", LOG_ERROR)
        return False

# ==================== 处理单个文件 ====================
def process_video(src: Path, config: dict, cache_dict: Dict[str, dict], log_func=None) -> bool:
    try:
        info = parse_filename(src.name, config, log_func)
        media_type = info.get("media_type")
        title = info.get("title")
        year = info.get("year")
        if not title or media_type not in ("movie", "tv"):
            if log_func:
                log_func(f"❌ 无法识别媒体类型: {src.name}", LOG_ERROR)
            return False

        year_str = year if year else "未知"
        if log_func:
            if media_type == "movie":
                log_func(f"🎬 识别为电影: {title} ({year_str})", LOG_SUCCESS)
            else:
                log_func(f"📺 识别为剧集: {title} S{info['season']:02d}E{info['episode']:02d}", LOG_SUCCESS)

        # 搜索 TMDB
        tmdb_result = search_tmdb(media_type, title, year, config, log_func)
        if not tmdb_result:
            return False

        tmdb_id = tmdb_result["id"]
        official_title = tmdb_result.get("title" if media_type == "movie" else "name", title)
        release_date = tmdb_result.get("release_date" if media_type == "movie" else "first_air_date", "")
        official_year = release_date[:4] if release_date else year

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
            episodes = get_tv_season_episodes(tmdb_id, season, config, log_func)
            ep_data = next((ep for ep in episodes if ep.get("episode_number") == episode), None)
            if not ep_data:
                if log_func: log_func(f"❌ TMDB 中无 S{season:02d}E{episode:02d} 数据", LOG_ERROR)
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
                    download_image(config["image_base_url"] + still, season_dir / "images" / img_name, log_func)
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

# ==================== 主流程 ====================
def run_processor_with_callback(config_path: str, progress_callback=None):
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
            try:
                if future.result():
                    success += 1
            except:
                pass
            if progress_callback:
                progress_callback(i, total, f"进度 {i}/{total}", LOG_PROGRESS)

    if config.get("incremental") and not config.get("dry_run"):
        save_cache(new_cache)
        log_func(f"💾 缓存已保存，共 {len(new_cache)} 条", LOG_SUCCESS)

    log_func(f"🎉 全部完成！成功处理 {success}/{total} 个文件", LOG_SUCCESS)

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