# -*- coding: utf-8 -*-
"""音频转录模块

调用 VideoCaptioner 开源项目的 BcutASR（必剪引擎），将音频文件转录为带时间戳的文本段落。
使用必剪引擎（BcutASR）：免费、无需 API Key、无需 GPU、无需登录。

为了避免打包体积过大以及运行环境缺少 ffmpeg，本模块直接实例化 BcutASR，绕过 ChunkedASR
与 pydub 的音频分块流程。BcutASR 本身仅将音频字节上传到 B站云 ASR 服务，不依赖本地 ffmpeg。
"""

import os
import sys
from typing import Callable, Optional

# 禁用环境代理（避免错误的代理环境变量导致 requests 请求失败）
# 必须在导入 VideoCaptioner（其内部使用 requests）之前设置
os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'


# 估算音频时长（秒），用于 BaseASR 内部的速率限制统计。
# 由于绕过了 pydub，不再调用 ffmpeg；对 192kbps CBR MP3 用文件大小估算即可。
def _estimate_audio_duration(file_binary: bytes) -> float:
    """根据文件大小估算音频时长（秒）

    当前输出固定为 192kbps CBR MP3，可用 bytes / (192000/8) 估算。
    对于其他格式，按保守值 192kbps 估算；若为空则返回最小值。
    """
    if not file_binary:
        return 0.01
    return len(file_binary) / 24000


def _resolve_vc_path() -> str:
    """解析 VideoCaptioner 项目路径

    优先级：
    1. PyInstaller 打包环境：_MEIPASS/VideoCaptioner-master
    2. 开发环境：项目根目录下的 VideoCaptioner-master
    """
    if hasattr(sys, '_MEIPASS'):
        packed_path = os.path.join(sys._MEIPASS, "VideoCaptioner-master")
        if os.path.isdir(packed_path):
            return packed_path

    dev_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "VideoCaptioner-master"
    )
    return dev_path


# 将 VideoCaptioner 项目路径加入 sys.path，以便导入其转录模块
VC_PATH = _resolve_vc_path()
if VC_PATH not in sys.path:
    sys.path.insert(0, VC_PATH)

from videocaptioner.core.asr.bcut import BcutASR
from videocaptioner.core.asr.base import BaseASR


# 绕过 pydub：直接替换 BaseASR 的音频时长计算方法，避免运行时报
# "ffmpeg not found" 或 JSONDecodeError（ffprobe 缺失导致）。
# BcutASR 上传的是原始文件字节，服务端完成解码，本地无需 ffmpeg。
def _get_audio_duration_patched(self) -> float:
    return _estimate_audio_duration(self.file_binary)


BaseASR._get_audio_duration = _get_audio_duration_patched


# 支持的音频文件扩展名
SUPPORTED_AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".flac"}


class AudioTranscriber:
    """音频转录器

    直接调用 VideoCaptioner 的 BcutASR（必剪引擎），将音频文件转录为带时间戳的文本段落。
    免费、无需 API Key、无需 GPU、无需登录，且不依赖本地 ffmpeg。
    """

    def __init__(self):
        """初始化转录器"""
        return

    def transcribe(
        self,
        audio_path: str,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> list[dict]:
        """转录音频文件为带时间戳的文本段落

        Args:
            audio_path: 音频文件路径（支持 mp3/wav/flac/m4a）
            progress_callback: 进度回调函数 callback(progress: int, message: str)
                              progress 为 0-100

        Returns:
            list[dict]: 段落列表，每个段落包含：
                - start_ms: 起始时间（毫秒，整数）
                - end_ms: 结束时间（毫秒，整数）
                - text: 转录文本（字符串）

        Raises:
            FileNotFoundError: 音频文件不存在
            RuntimeError: 转录失败
        """
        # 检查音频文件是否存在
        if not os.path.isfile(audio_path):
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")

        # 检查文件扩展名是否为支持的格式
        _, ext = os.path.splitext(audio_path)
        ext_lower = ext.lower()
        if ext_lower not in SUPPORTED_AUDIO_EXTENSIONS:
            raise RuntimeError(
                f"不支持的音频格式: {ext or '(无扩展名)'}，"
                f"仅支持: {', '.join(sorted(SUPPORTED_AUDIO_EXTENSIONS))}"
            )

        # 直接调用 BcutASR，绕过 ChunkedASR/pydub
        try:
            asr = BcutASR(
                audio_path,
                use_cache=False,
                need_word_time_stamp=False,
            )
            asr_data = asr.run(callback=progress_callback)
        except Exception as e:
            raise RuntimeError(f"转录过程失败: {e}") from e

        # 检查转录结果是否为空
        if asr_data is None or not asr_data.segments:
            raise RuntimeError("转录结果为空，未获取到任何文本段落")

        # 遍历 segments，转换为接口要求的格式
        segments: list[dict] = []
        for seg in asr_data.segments:
            text = seg.text.strip() if seg.text else ""
            if text:
                segments.append(
                    {
                        "start_ms": seg.start_time,
                        "end_ms": seg.end_time,
                        "text": text,
                    }
                )

        # 再次校验转换后的结果
        if not segments:
            raise RuntimeError("转录结果为空，未获取到任何文本段落")

        return segments
