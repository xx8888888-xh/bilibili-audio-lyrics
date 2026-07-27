# -*- coding: utf-8 -*-
"""调试B站字幕API响应"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bilibili_lyrics.bilibili_downloader import BilibiliAudioDownloader

URL = "https://www.bilibili.com/video/BV1hs411W7uR/?spm_id_from=333.337.search-card.all.click&vd_source=7b76ed3c0890a62104ee1d59ca9859ce"


def main():
    downloader = BilibiliAudioDownloader()
    bvid, page = downloader.parse_url(URL)
    print(f"bvid={bvid}, page={page}")
    cid, part_title = downloader._get_cid(bvid, page)
    print(f"cid={cid}, part={part_title}")

    for name, endpoint in [
        ("wbi/v2", "https://api.bilibili.com/x/player/wbi/v2"),
        ("v2", "https://api.bilibili.com/x/player/v2"),
    ]:
        print(f"\n--- x/player/{name} ---")
        try:
            if "wbi" in endpoint:
                img_key, sub_key = downloader._get_wbi_keys()
                from bilibili_lyrics.bilibili_downloader import _build_wbi_params
                params = _build_wbi_params({"bvid": bvid, "cid": cid}, img_key, sub_key)
            else:
                params = {"bvid": bvid, "cid": cid}

            resp = downloader.session.get(
                endpoint,
                params=params,
                headers=downloader._get_headers(bvid),
                timeout=15,
            )
            print(f"status={resp.status_code}")
            data = resp.json()
            subtitle = data.get('data', {}).get('subtitle', {})
            print("subtitle 字段:")
            print(json.dumps(subtitle, ensure_ascii=False, indent=2))
            print(f"\nsubtitle 键列表: {list(subtitle.keys())}")
        except Exception as e:
            print(f"错误: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
