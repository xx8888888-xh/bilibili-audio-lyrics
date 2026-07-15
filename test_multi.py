# -*- coding: utf-8 -*-
"""多链接批量处理测试

测试两个链接的并行处理：
1. BV1rY4y1y7r9 (用户指定)
2. BV1GJ411x7h7 (已验证可用)
"""

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from bilibili_lyrics.bilibili_downloader import BilibiliAudioDownloader
from bilibili_lyrics.transcriber import AudioTranscriber
from bilibili_lyrics.lrc_generator import generate_lrc


def process_single_url(url: str, output_dir: str) -> dict:
    """处理单个URL：下载→转录→生成歌词"""
    result_info = {"url": url, "success": False, "error": None,
                   "audio_path": None, "lrc_path": None, "segments_count": 0}
    try:
        print(f"\n[{url}] 开始处理...")

        # 步骤1: 下载音频
        print(f"[{url}] [1/3] 下载音频...")
        downloader = BilibiliAudioDownloader()
        result = downloader.download(url, output_dir)
        audio_path = result["audio_path"]
        title = result["title"]
        result_info["audio_path"] = audio_path
        print(f"[{url}] 下载完成: {os.path.basename(audio_path)} "
              f"({os.path.getsize(audio_path)/1024/1024:.2f} MB)")

        # 步骤2: 转录音频
        print(f"[{url}] [2/3] 转录音频...")
        transcriber = AudioTranscriber()
        segments = transcriber.transcribe(audio_path)
        result_info["segments_count"] = len(segments)
        print(f"[{url}] 转录完成: {len(segments)} 段")

        # 步骤3: 生成LRC歌词
        print(f"[{url}] [3/3] 生成LRC歌词...")
        safe_title = "".join(
            c if c not in r'\/:*?"<>|' else "_" for c in title
        )
        lrc_path = os.path.join(output_dir, f"{safe_title}.lrc")
        generate_lrc(segments, lrc_path,
                     metadata={"title": title, "by": "B站歌词生成器"})
        result_info["lrc_path"] = lrc_path
        result_info["success"] = True
        print(f"[{url}] 歌词已生成: {lrc_path}")

    except Exception as e:
        result_info["error"] = f"{type(e).__name__}: {e}"
        print(f"[{url}] ❌ 失败: {result_info['error']}")

    return result_info


def main():
    # 测试链接列表
    test_urls = [
        "https://www.bilibili.com/video/BV1rY4y1y7r9?vd_source=7b76ed3c0890a62104ee1d59ca9859ce",
        "https://www.bilibili.com/video/BV1GJ411x7h7",
    ]

    output_dir = os.path.join(PROJECT_ROOT, "test_output_multi")
    os.makedirs(output_dir, exist_ok=True)

    print("=" * 70)
    print("多链接批量并行处理测试")
    print("=" * 70)
    print(f"测试链接数: {len(test_urls)}")
    print(f"并行数: 2")
    print(f"输出目录: {output_dir}")
    for i, url in enumerate(test_urls, 1):
        print(f"  [{i}] {url}")

    t_start = time.time()

    # 使用线程池并行处理（2个并行）
    results = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_to_url = {
            executor.submit(process_single_url, url, output_dir): url
            for url in test_urls
        }
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                results.append({
                    "url": url, "success": False,
                    "error": f"{type(e).__name__}: {e}"
                })

    t_total = time.time() - t_start

    # 汇总结果
    print("\n" + "=" * 70)
    print("测试结果汇总")
    print("=" * 70)
    success_count = 0
    for r in results:
        status = "✅ 成功" if r["success"] else "❌ 失败"
        print(f"\n{r['url']}")
        print(f"  状态: {status}")
        if r["success"]:
            success_count += 1
            print(f"  音频: {r['audio_path']}")
            print(f"  歌词: {r['lrc_path']}")
            print(f"  段落数: {r['segments_count']}")
            # 显示LRC前5行
            if os.path.exists(r["lrc_path"]):
                with open(r["lrc_path"], "r", encoding="utf-8") as f:
                    lines = f.read().strip().split("\n")
                print(f"  LRC预览（前5行）:")
                for line in lines[:5]:
                    print(f"    {line}")
        else:
            print(f"  错误: {r['error']}")

    print("\n" + "=" * 70)
    print(f"总计: 成功 {success_count}/{len(test_urls)}, 总耗时 {t_total:.1f}s")
    print("=" * 70)

    if success_count == len(test_urls):
        print("\n✅ 全部测试通过！多链接并行处理功能正常。")
    else:
        print(f"\n⚠ {len(test_urls) - success_count} 个链接处理失败，请检查。")
        sys.exit(1)


if __name__ == "__main__":
    main()
