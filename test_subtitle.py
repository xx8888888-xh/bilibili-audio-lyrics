# -*- coding: utf-8 -*-
"""测试B站官方字幕获取"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bilibili_lyrics.bilibili_downloader import BilibiliAudioDownloader

URLS = [
    ("BV1hs411W7uR", "https://www.bilibili.com/video/BV1hs411W7uR/?spm_id_from=333.337.search-card.all.click&vd_source=7b76ed3c0890a62104ee1d59ca9859ce"),
    ("BV1uJ411879Y", "https://www.bilibili.com/video/BV1uJ411879Y/?spm_id_from=333.337.search-card.all.click&vd_source=7b76ed3c0890a62104ee1d59ca9859ce"),
]


def main():
    downloader = BilibiliAudioDownloader()
    for bvid, url in URLS:
        print(f"\n{'='*60}")
        print(f"测试: {bvid}")
        print(f"URL: {url}")
        print(f"{'='*60}")
        try:
            result = downloader.get_official_subtitle(
                url, preferred_langs=["ja", "en", "zh-CN"]
            )
            if result:
                segments, lang = result
                print(f"✅ 找到官方字幕，语言: {lang}，共 {len(segments)} 段")
                for seg in segments[:5]:
                    print(f"  [{seg['start_ms']:>7}] {seg['text']}")
                if len(segments) > 5:
                    print(f"  ... 还有 {len(segments)-5} 段")
            else:
                print("❌ 未找到官方字幕")
        except Exception as e:
            print(f"💥 错误: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
