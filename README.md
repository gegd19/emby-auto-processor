# 🚀 Emby Auto Processor 快速开始


## 📋 环境要求

- **Python 3.8+**  
  > 检查方法：在终端输入 `python --version` 或 `python3 --version`
- **网络连接**（用于访问 TMDB 和 AI 接口）
- **推荐：TMDB API 密钥**  
  > [点击免费申请](https://www.themoviedb.org/settings/api) → 注册账号 → 进入 API 页面申请开发者密钥
- **可选：DeepSeek / OpenAI 等 API 密钥**  
  > 用于 AI 增强功能（如智能解析剧集名、自动生成剧情简介）

## 🔧 安装与配置

### 1. 克隆仓库
```bash
git clone https://github.com/gegd19/emby-auto-processor.git
cd emby-auto-processor
```
> 💡 如果没有安装 Git，也可以直接下载 ZIP 包解压。

### 2. 创建并激活虚拟环境（推荐）
> **为什么需要虚拟环境？**  
> 避免不同项目之间的 Python 包版本冲突。

#### Windows PowerShell
```bash
python -m venv .venv          # 创建虚拟环境文件夹
.venv\Scripts\Activate.ps1    # 激活（注意：若报错需先执行 Set-ExecutionPolicy RemoteSigned）
```
> ⚠️ 如果 PowerShell 禁止执行脚本，可以改用 CMD：  
> `.venv\Scripts\activate.bat`

#### Linux / macOS
```bash
python3 -m venv .venv
source .venv/bin/activate
```
> 激活成功后，命令行提示符前会出现 `(.venv)` 字样。

### 3. 安装依赖
```bash
pip install -r requirements.txt
```
> 这会自动安装所有必需的第三方库（如 requests、flask 等）。

### 4. 准备配置文件
```bash
# Windows PowerShell
Copy-Item auto_config.example.json auto_config.json

# Linux / macOS
cp auto_config.example.json auto_config.json
```


### 5. 编辑 `auto_config.json`
用文本编辑器（如 VS Code、Notepad++、Sublime）打开 `auto_config.json`，填入以下内容：

| 字段 | 说明 | 示例 |
|------|------|------|
| `tmdb_api.api_key` | **必填**。你的 TMDB API 密钥 | `"8f1e2d3c4b5a6..."` |
| `source_folders` | 存放未处理视频的源文件夹路径（支持多个） | `["D:/downloads", "/home/user/videos"]` |
| `tv_target_folder` | Emby 的电视剧媒体库目录 | `"E:/emby/TV Shows"` |
| `movie_target_folder` | Emby 的电影媒体库目录 | `"E:/emby/Movies"` |

**AI 功能（可选）**  
如需使用 AI 解析或剧情增强，将以下字段的 `enabled` 改为 `true`，并填写对应的 `api_key`：
```json
"ai_parser": {
    "enabled": true,
    "api_key": "sk-xxxxx",
    "model": "deepseek-chat"
},
"ai_plot_enhance": {
    "enabled": true,
    "api_key": "sk-xxxxx"
}
```
> 🔐 请妥善保管 API 密钥，不要上传到公开代码仓库。

### 6. 启动 Web 服务
```bash
python web_app.py
```
成功启动后，终端会显示：
```
* Running on http://127.0.0.1:5000
```
用浏览器打开该地址，即可使用可视化界面。

## 💡 命令行模式（备选）
如果你不需要 Web 界面，可以直接运行核心处理脚本：
```bash
# 查看所有命令行参数
python emby_auto_processor.py --help

# 使用默认配置开始处理
python emby_auto_processor.py
```
> 命令行模式适合定时任务（如配合 cron 或任务计划程序）。

---

## ✅ 验证是否成功
1. 访问 `http://127.0.0.1:5000` 能看到界面 → Web 服务正常  
2. 点击“开始处理”后，Emby 媒体库中出现整理好的剧集/电影 → 配置正确  

## ❓ 常见问题
- **激活虚拟环境时提示“无法加载脚本”**  
  以管理员身份运行 PowerShell，执行 `Set-ExecutionPolicy RemoteSigned` 后重试。
- **TMDB 识别不准确**  
  在 `auto_config.json` 中调整 `tmdb_api.language` 为 `"zh-CN"` 可获得中文结果。
- **AI 功能无反应**  
  检查 API 密钥是否有效、账户是否有余额（DeepSeek 等需要付费）。

---


**⚙️ 配置亮点
核心功能	配置项	说明
双模式支持	movie_target_folder	电影和剧集自动分流，分别存入独立目录
AI 智能解析	ai_parser.enabled	开启后，文件名识别准确率大幅提升
AI 简介润色	ai_plot_enhance.enabled	让你的媒体库简介充满大片质感
可视化日志	Web 界面	彩色区分日志级别，问题排查一目了然
完整的配置项说明请参考 auto_config.example.json 文件内的注释。**

## 📂 处理后的目录结构  ##

![处理后的目录结构](https://github.com/user-attachments/assets/29420f11-9e5a-441b-88e4-32c7b19b459f)

## 🤝 贡献与反馈  ##
这是一个充满热情的开源项目，欢迎任何形式的贡献！

遇到问题？请提交 **Issue**

有好的想法？欢迎发起 ** Pull **

觉得有用？⭐ Star 是对我最大的鼓励！

## 📜 开源协议  ##
本项目基于 MIT License 开源，请放心使用。

<p align="center"> <b>Made with ❤️ for all home media enthusiasts.</b> </p> ```
