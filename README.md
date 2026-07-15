# B站音频歌词生成器

基于 [VideoCaptioner](https://github.com/WEIFENG2333/VideoCaptioner.git) 和 [BilibiliDown](https://github.com/nICEnnnnnnnLee/BilibiliDown.git) 开源项目开发的自动化软件。

## 功能

1. **图形界面**：简洁的PyQt5界面，支持批量多链接处理
2. **音频下载**：自动下载B站视频的音频流（WBI签名+DASH流+ffmpeg转封装）
3. **音频转录**：调用VideoCaptioner的必剪引擎（BcutASR），免费、无需API Key
4. **歌词生成**：生成标准LRC歌词文件，主流音乐播放器可同步显示

## 使用方法

### 方式一：直接运行exe（推荐）

下载 `dist/BilibiliAudioLyrics.exe`，双击运行即可。

### 方式二：从源码运行

```bash
# 1. 克隆仓库
git clone https://github.com/你的用户名/bilibili-audio-lyrics.git
cd bilibili-audio-lyrics

# 2. 克隆依赖的开源项目
git clone https://github.com/WEIFENG2333/VideoCaptioner.git VideoCaptioner-master

# 3. 安装依赖
pip install -r requirements.txt

# 4. 运行
python main.py
```

## 使用说明

1. 启动软件后，在输入框中粘贴B站视频链接（每行一个，支持批量）
2. 选择输出目录
3. 设置并行任务数（建议2-3）
4. 点击"开始生成歌词"
5. 等待处理完成，输出目录会生成 `.m4a` 音频文件和 `.lrc` 歌词文件

## 支持的链接格式

- `https://www.bilibili.com/video/BVxxxxx`
- `https://www.bilibili.com/video/BVxxxxx?p=2`（分P）
- `https://b23.tv/xxx`（短链）
- 纯BV号 `BVxxxxx`

## 输出文件

- **音频文件**：`.m4a` 格式（AAC编码，192Kbps）
- **歌词文件**：`.lrc` 格式（UTF-8编码，2位百分秒时间戳，最大兼容性）

将 `.lrc` 文件与 `.m4a` 文件放在同一目录下且同名，主流音乐播放器（QQ音乐、网易云音乐、酷狗等）会自动加载并同步显示歌词。

## 技术架构

- `bilibili_lyrics/bilibili_downloader.py`：B站音频下载（WBI签名+DASH流）
- `bilibili_lyrics/transcriber.py`：音频转录（VideoCaptioner必剪引擎）
- `bilibili_lyrics/lrc_generator.py`：LRC歌词生成
- `bilibili_lyrics/gui.py`：PyQt5图形界面（支持多链接并行）
- `main.py`：程序入口

## 依赖

- Python 3.10+
- requests, pydub, diskcache, langdetect, openai, PyQt5
- ffmpeg（需加入PATH）

## 许可证

本项目仅供学习交流使用。
