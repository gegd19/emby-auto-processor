# 🎬 Emby Auto Processor —— 你的全自动 AI 媒体库管家

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS%20%7C%20NAS-lightgrey)]()

**告别手动整理文件的繁琐，让 AI 帮你打理一切。**

还在为 PT 下载的电影、剧集文件名混乱而头疼？还在手动创建文件夹、重命名、刮削元数据？**Emby Auto Processor** 正是为你打造的终极解决方案。它不仅能精准识别电影和剧集，更能调用 AI 大模型改写简介，最后通过**硬链接**瞬间完成入库，**零空间占用，保种入库两不误**。

---

## ✨ 为什么选择它？—— 三大核心优势

### 🚀 创新性：AI 深度赋能，不只是重命名
- **智能媒体识别**：内置 AI + 正则双引擎，自动判断文件是**电影**还是**剧集**，并提取准确名称、年份、季集号。告别复杂的命名规则。
- **剧情简介润色**：接入 DeepSeek / OpenAI 等大模型，将 TMDB 的平淡简介改写为**悬念迭起、引人入胜**的文案。Web 界面支持**流式预览**，实时感受 AI 的文字魅力。
- **流式交互体验**：首创在媒体整理工具中集成 SSE 流式传输，AI 改写过程逐字呈现，科技感拉满。

### 🛠️ 实用性：一站式全自动闭环
- **TMDB 无缝对接**：自动搜索并匹配 TMDB 官方数据，获取标准中文名、年份、简介、评分、演职员信息。
- **元数据全生成**：自动生成 Emby / Jellyfin 完美兼容的 `tvshow.nfo`、`season.nfo`、`movie.nfo` 及单集 NFO 文件。
- **海报图片下载**：自动下载剧集海报、背景图（fanart）以及每集的剧照，让媒体库不再单调。
- **增量处理缓存**：记录每一个成功处理的文件，后续运行**秒级跳过**，只专注于新增内容。

### 🎯 易用性：从命令行到可视化，总有一款适合你
- **🌐 全功能 Web 控制面板**：
  - **可视化配置**：所有设置项一目了然，勾勾选选即可完成配置，无需手写 JSON。
  - **目录浏览**：点击按钮即可在服务器上选择文件夹，路径自动填入。
  - **实时进度监控**：彩色日志流式输出，TMDB 搜索、图片下载、AI 调用过程**全透明**。
- **⌨️ 命令行模式**：极客首选，一行命令即可静默运行，适合集成到自动化脚本或 NAS 任务计划中。
- **💾 硬链接零空间**：采用文件系统级的硬链接（Hard Link），入库后的文件**不占用额外磁盘空间**，源文件可继续做种上传。

---

## 📸 界面预览

| 配置面板 | 实时日志与流式 AI 测试 |
| :---: | :---: |
| ![配置面板](https://github.com/user-attachments/assets/c8a32ac8-7ec6-43dd-926f-dab21f9fd7cf) | ![流式AI](https://github.com/user-attachments/assets/6754189d-f328-4069-8985-b6edbbec0fdf) |

---

## 🚀 快速开始

### 📋 环境要求
- Python 3.8+
- 网络连接（用于访问 TMDB 和 AI 接口）
- 推荐：TMDB API 密钥（[免费申请](https://www.themoviedb.org/settings/api)）
- 可选：DeepSeek / OpenAI 等 API 密钥（用于 AI 增强功能）

### 🔧 安装与配置
1. **克隆仓库**
   ```bash
   git clone https://github.com/shuzhuhua/gegd19/emby-auto-processor.git
   cd emby-auto-processor
2.  **安装依赖** 
   pip install -r requirements.txt

3. **准备配置文件**
   cp auto_config.example.json auto_config.json
  # 编辑 auto_config.json，填入你的 TMDB API Key 和文件夹路径

4.**启动 Web 服务**

   访问 http://127.0.0.1:5000，享受丝滑的视觉化操作！

  💡  命令行模式：如果你不需要 Web 界面，可以直接运行 python emby_auto_processor.py --help 查看参数，或直接执行 python emby_auto_processor.py 开始处理。

**⚙️ 配置亮点
核心功能	配置项	说明
双模式支持	movie_target_folder	电影和剧集自动分流，分别存入独立目录
AI 智能解析	ai_parser.enabled	开启后，文件名识别准确率大幅提升
AI 简介润色	ai_plot_enhance.enabled	让你的媒体库简介充满大片质感
可视化日志	Web 界面	彩色区分日志级别，问题排查一目了然
完整的配置项说明请参考 auto_config.example.json 文件内的注释。**

📂 处理后的目录结构
## 📂 处理后的目录结构

(https://github.com/user-attachments/assets/29420f11-9e5a-441b-88e4-32c7b19b459f)

🤝 贡献与反馈
这是一个充满热情的开源项目，欢迎任何形式的贡献！

遇到问题？请提交 Issue

有好的想法？欢迎发起 Pull Request

觉得有用？⭐ Star 是对我最大的鼓励！

📜 开源协议
本项目基于 MIT License 开源，请放心使用。

<p align="center"> <b>Made with ❤️ for all home media enthusiasts.</b> </p> ```
