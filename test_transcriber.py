# -*- coding: utf-8 -*-
"""测试转录模块"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bilibili_lyrics.transcriber import AudioTranscriber


def main():
    audio_path = r"c:\Users\xx\Desktop\bilibili_video_download\test_ja_2\【初音ミク】妄想感傷代償連盟【DECO_27】.mp3"
    print(f"测试音频: {audio_path}")
    print("开始转录（日语 Whisper.cpp）...")

    transcriber = AudioTranscriber()

    def progress(p, m):
        print(f"[{p:3d}%] {m}")

    segments = transcriber.transcribe(audio_path, language="ja", progress_callback=progress)
    print(f"\n转录完成，共 {len(segments)} 段")
    for seg in segments[:10]:
        print(f"  [{seg['start_ms']:>7}] {seg['text']}")


if __name__ == "__main__":
    main()
