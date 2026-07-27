# -*- coding: utf-8 -*-
"""音频转录模块

调用 VideoCaptioner 开源项目的转录功能，将音频文件转录为带时间戳的文本段落。
使用必剪引擎（BcutASR），免费、无需 API Key、无需 GPU、无需登录。
"""

import os
import sys
from typing import Callable, Optional

# 禁用环境代理（避免错误的代理环境变量导致 requests 请求失败）
# 必须在导入 VideoCaptioner（其内部使用 requests）之前设置
os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'


def _resolve_vc_path() -> str:
    """解析 VideoCaptioner 项目路径

    优先级：
    1. PyInstaller 打包环境：_MEIPASS/VideoCaptioner-master
    2. 开发环境：项目根目录下的 VideoCaptioner-master
    """
    # PyInstaller 打包后，资源会被解压到 sys._MEIPASS
    if hasattr(sys, '_MEIPASS'):
        packed_path = os.path.join(sys._MEIPASS, "VideoCaptioner-master")
        if os.path.isdir(packed_path):
            return packed_path

    # 开发环境：bilibili_lyrics/ 的父目录下的 VideoCaptioner-master
    dev_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "VideoCaptioner-master"
    )
    return dev_path


# 将 VideoCaptioner 项目路径加入 sys.path，以便导入其转录模块
VC_PATH = _resolve_vc_path()
if VC_PATH not in sys.path:
    sys.path.insert(0, VC_PATH)

from videocaptioner.core.asr.transcribe import transcribe
from videocaptioner.core.entities import TranscribeConfig, TranscribeModelEnum


# 支持的音频文件扩展名
SUPPORTED_AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".flac"}


class AudioTranscriber:
    """音频转录器

    封装 VideoCaptioner 的转录功能，将音频文件转录为带时间戳的文本段落。
    默认使用必剪引擎（BcutASR）：免费、无需 API Key、无需 GPU、无需登录。
    """

    def __init__(self):
        """初始化转录器

        VideoCaptioner 路径已在模块导入时加入 sys.path，此处无需额外操作。
        """
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

        # 构建转录配置：必剪引擎，自动检测语言，句级时间戳
        config = TranscribeConfig(
            transcribe_model=TranscribeModelEnum.BIJIAN,  # 必剪引擎，免费
            transcribe_language="",  # 空字符串=自动检测语言
            need_word_time_stamp=False,  # 句级时间戳（不是词级），适合生成歌词
        )

        # 调用 VideoCaptioner 进行转录
        try:
            asr_data = transcribe(audio_path, config, callback=progress_callback)
        except Exception as e:
            # 捕获转录过程中的异常，包装为 RuntimeError 抛出
            raise RuntimeError(f"转录过程失败: {e}") from e

        # 检查转录结果是否为空
        if asr_data is None or not asr_data.segments:
            raise RuntimeError("转录结果为空，未获取到任何文本段落")

        # 遍历 segments，转换为接口要求的格式
        segments: list[dict] = []
        for seg in asr_data.segments:
            segments.append(
                {
                    "start_ms": seg.start_time,
                    "end_ms": seg.end_time,
                    "text": seg.text.strip(),
                }
            )

        # 再次校验转换后的结果
        if not segments:
            raise RuntimeError("转录结果为空，未获取到任何文本段落")

        return segments
