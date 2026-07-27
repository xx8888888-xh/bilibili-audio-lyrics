# -*- coding: utf-8 -*-
"""B站音频歌词生成器 - 程序入口

支持两种启动方式：
1. GUI 模式：直接双击运行，或通过 `python main.py` 启动
2. 命令行模式：`python main.py --url <URL> [--output-dir <DIR>]`
   自动完成下载、转录、生成歌词，无需人工干预
"""

import sys
import os
import argparse

# 确保项目目录在sys.path中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


DEFAULT_OUTPUT_FOLDER_NAME = "哔哩哔哩 video 下载"


def _default_output_dir() -> str:
    """返回默认输出目录：用户下载目录下的 '哔哩哔哩 video 下载' 文件夹

    第一次运行或目录不存在时会自动创建。
    """
    downloads = os.path.join(os.path.expanduser("~"), "Downloads")
    if sys.platform == "win32" and not os.path.isdir(downloads):
        downloads = os.path.join(os.path.expanduser("~"), "下载")
    output_dir = os.path.join(downloads, DEFAULT_OUTPUT_FOLDER_NAME)
    os.makedirs(output_dir, exist_ok=True)
    return output_dir


def _run_cli(url: str, output_dir: str, auto_open: bool = False) -> None:
    """命令行模式：下载 → 转录 → 生成 LRC"""
    from bilibili_lyrics.bilibili_downloader import BilibiliAudioDownloader
    from bilibili_lyrics.transcriber import AudioTranscriber
    from bilibili_lyrics.lrc_generator import generate_lrc

    os.makedirs(output_dir, exist_ok=True)
    print(f"输出目录: {output_dir}")

    def progress(p: int, msg: str) -> None:
        print(f"[{p:3d}%] {msg}")

    # 1. 下载音频
    print(f"开始下载: {url}")
    downloader = BilibiliAudioDownloader()
    result = downloader.download(url, output_dir, progress_callback=progress)
    audio_path = result["audio_path"]
    title = result["title"]
    print(f"音频已保存: {audio_path}")

    # 2. 转录音频
    print("开始转录音频...")
    transcriber = AudioTranscriber()
    segments = transcriber.transcribe(audio_path, progress_callback=progress)
    print(f"转录完成，共 {len(segments)} 段")

    # 3. 生成 LRC
    safe_title = "".join(c if c not in r'\/:*?"<>|' else "_" for c in title)
    lrc_path = os.path.join(output_dir, f"{safe_title}.lrc")
    generate_lrc(segments, lrc_path, metadata={"title": title})
    print(f"歌词已保存: {lrc_path}")

    if auto_open:
        os.startfile(output_dir)

    print("全部完成")


def _run_gui() -> None:
    """GUI 模式"""
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtGui import QFont
    from bilibili_lyrics.gui import MainWindow

    app = QApplication(sys.argv)
    app.setFont(QFont("微软雅黑", 10))
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


def main() -> None:
    """程序入口"""
    parser = argparse.ArgumentParser(
        description="B站音频歌词生成器",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--url", "-u", type=str, help="B站视频链接（提供此参数时进入命令行模式，自动下载并生成歌词）")
    parser.add_argument(
        "--output-dir", "-o", type=str,
        default=None,
        help="输出目录（默认：下载目录/哔哩哔哩 video 下载）",
    )
    parser.add_argument(
        "--auto-open", action="store_true",
        help="命令行模式下完成后自动打开输出目录",
    )
    args = parser.parse_args()

    if args.url:
        output_dir = args.output_dir or _default_output_dir()
        _run_cli(args.url, output_dir, auto_open=args.auto_open)
    else:
        _run_gui()


if __name__ == "__main__":
    main()
