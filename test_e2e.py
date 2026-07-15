# -*- coding: utf-8 -*-
"""端到端集成测试：下载B站音频 → 转录 → 生成LRC歌词"""

import os
import sys
import time

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from bilibili_lyrics.bilibili_downloader import BilibiliAudioDownloader
from bilibili_lyrics.transcriber import AudioTranscriber
from bilibili_lyrics.lrc_generator import generate_lrc


def progress_callback(progress: int, message: str):
    """进度回调"""
    print(f"  [{progress:3d}%] {message}")


def main():
    # 测试视频：Rick Astley - Never Gonna Give You Up (英文歌曲MV)
    # 子agent已验证此视频可成功下载
    test_url = "https://www.bilibili.com/video/BV1GJ411x7h7"
    output_dir = os.path.join(PROJECT_ROOT, "test_output")
    os.makedirs(output_dir, exist_ok=True)

    print("=" * 60)
    print("端到端集成测试")
    print("=" * 60)
    print(f"测试视频: {test_url}")
    print(f"输出目录: {output_dir}")
    print()

    # ========== 步骤1: 下载音频 ==========
    print("[步骤1/3] 下载B站音频...")
    t0 = time.time()
    downloader = BilibiliAudioDownloader()
    try:
        result = downloader.download(test_url, output_dir, progress_callback=progress_callback)
    except Exception as e:
        print(f"下载失败: {type(e).__name__}: {e}")
        sys.exit(1)

    audio_path = result["audio_path"]
    title = result["title"]
    bvid = result["bvid"]
    cid = result["cid"]
    t1 = time.time()
    print(f"下载完成! 耗时 {t1-t0:.1f}s")
    print(f"  音频路径: {audio_path}")
    print(f"  视频标题: {title}")
    print(f"  BV号: {bvid}")
    print(f"  CID: {cid}")
    print(f"  文件大小: {os.path.getsize(audio_path)/1024/1024:.2f} MB")
    print()

    # ========== 步骤2: 转录音频 ==========
    print("[步骤2/3] 转录音频（调用VideoCaptioner必剪引擎）...")
    t2 = time.time()
    transcriber = AudioTranscriber()
    try:
        segments = transcriber.transcribe(audio_path, progress_callback=progress_callback)
    except Exception as e:
        print(f"转录失败: {type(e).__name__}: {e}")
        sys.exit(1)
    t3 = time.time()
    print(f"转录完成! 耗时 {t3-t2:.1f}s")
    print(f"  段落数: {len(segments)}")
    if segments:
        print(f"  首段: [{segments[0]['start_ms']}ms-{segments[0]['end_ms']}ms] {segments[0]['text'][:50]}")
        print(f"  末段: [{segments[-1]['start_ms']}ms-{segments[-1]['end_ms']}ms] {segments[-1]['text'][:50]}")
    print()

    # ========== 步骤3: 生成LRC歌词 ==========
    print("[步骤3/3] 生成LRC歌词文件...")
    # 文件名安全化
    safe_title = "".join(c if c not in r'\/:*?"<>|' else "_" for c in title)
    lrc_path = os.path.join(output_dir, f"{safe_title}.lrc")
    lrc_content = generate_lrc(
        segments, lrc_path,
        metadata={"title": title, "by": "B站歌词生成器"},
        ms_digits=2,  # 2位百分秒，最大兼容性
    )
    print(f"LRC歌词已生成: {lrc_path}")
    print(f"  文件大小: {os.path.getsize(lrc_path)} 字节")
    print()

    # ========== 验证LRC文件 ==========
    print("=" * 60)
    print("LRC文件内容预览（前15行）:")
    print("=" * 60)
    lrc_lines = lrc_content.strip().split("\n")
    for line in lrc_lines[:15]:
        print(f"  {line}")
    if len(lrc_lines) > 15:
        print(f"  ... (共 {len(lrc_lines)} 行)")
    print()

    # 验证LRC格式
    print("=" * 60)
    print("格式验证:")
    print("=" * 60)
    import re
    timestamp_pattern = re.compile(r'^\[\d{2}:\d{2}\.\d{2}\]')
    metadata_pattern = re.compile(r'^\[(ti|ar|al|by|offset):')

    metadata_count = 0
    lyric_count = 0
    invalid_lines = 0

    for line in lrc_lines:
        if metadata_pattern.match(line):
            metadata_count += 1
        elif timestamp_pattern.match(line):
            lyric_count += 1
        elif line.strip() == "":
            continue
        else:
            invalid_lines += 1
            print(f"  ⚠ 无效行: {line}")

    print(f"  元数据标签数: {metadata_count}")
    print(f"  歌词行数: {lyric_count}")
    print(f"  无效行数: {invalid_lines}")

    # 验证编码
    with open(lrc_path, "rb") as f:
        raw = f.read(3)
    has_bom = raw[:3] == b'\xef\xbb\xbf'
    print(f"  UTF-8 BOM: {'有' if has_bom else '无（正确）'}")

    # 验证换行符
    with open(lrc_path, "rb") as f:
        content_bytes = f.read()
    has_crlf = b'\r\n' in content_bytes
    print(f"  换行符: {'CRLF' if has_crlf else 'LF（正确）'}")

    if invalid_lines == 0 and not has_bom and not has_crlf and lyric_count > 0:
        print()
        print("=" * 60)
        print("✅ 端到端测试通过！所有模块正常工作。")
        print("=" * 60)
        print(f"  音频文件: {audio_path}")
        print(f"  歌词文件: {lrc_path}")
        print(f"  总耗时: {t3-t0:.1f}s")
    else:
        print()
        print("=" * 60)
        print("❌ 测试发现问题，请检查上述输出。")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
