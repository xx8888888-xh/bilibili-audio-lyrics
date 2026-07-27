# -*- coding: utf-8 -*-
"""音频转录模块

支持两种转录引擎：
1. 中文：调用 VideoCaptioner 的 BcutASR（必剪引擎），免费、无需 API Key、无需 GPU、无需登录。
2. 日语/英语：调用本地 Whisper.cpp（small 模型），本地运行、不依赖云服务、准确率更高。

为了避免打包体积过大以及运行环境缺少 ffmpeg，中文路径直接实例化 BcutASR，绕过 ChunkedASR
与 pydub 的音频分块流程。BcutASR 本身仅将音频字节上传到 B站云 ASR 服务，不依赖本地 ffmpeg。
"""

import os
import re
import sys
import subprocess
import tempfile
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

    根据语言自动选择转录引擎：
    - 中文（zh）：使用 BcutASR（必剪引擎）
    - 日语（ja）、英语（en）：使用本地 Whisper.cpp + small 模型
    """

    # Whisper.cpp 默认超时（秒）：长音频识别可能很慢
    WHISPER_TIMEOUT = 1800

    def __init__(self):
        """初始化转录器"""
        return

    @staticmethod
    def _resolve_whisper_cli() -> str:
        """解析本地 whisper-cli.exe 路径

        优先级：
        1. PyInstaller 打包环境：_MEIPASS/whisper_test/Release/whisper-cli.exe
        2. 开发环境：项目根目录/whisper_test/Release/whisper-cli.exe
        """
        exe_name = "whisper-cli.exe"
        if hasattr(sys, '_MEIPASS'):
            packed_path = os.path.join(sys._MEIPASS, "whisper_test", "Release", exe_name)
            if os.path.isfile(packed_path):
                return packed_path

        dev_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "whisper_test", "Release", exe_name
        )
        return dev_path

    @staticmethod
    def _resolve_whisper_model() -> str:
        """解析本地 Whisper small 模型路径

        优先级：
        1. PyInstaller 打包环境：_MEIPASS/models/ggml-small.bin
        2. 开发环境：项目根目录/models/ggml-small.bin
        """
        model_name = "ggml-small.bin"
        if hasattr(sys, '_MEIPASS'):
            packed_path = os.path.join(sys._MEIPASS, "models", model_name)
            if os.path.isfile(packed_path):
                return packed_path

        dev_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "models", model_name
        )
        return dev_path

    @staticmethod
    def _parse_srt(srt_text: str) -> list[dict]:
        """将 SRT 字幕文本解析为段落列表

        Returns:
            list[dict]: 每个段落包含 start_ms、end_ms、text
        """
        pattern = re.compile(
            r'\d+\s+'
            r'(\d{2}):(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*'
            r'(\d{2}):(\d{2}):(\d{2})[.,](\d{3})\s+'
            r'(.+?)(?=\n\s*\n|\Z)',
            re.DOTALL
        )
        segments = []
        for match in pattern.finditer(srt_text):
            h1, m1, s1, ms1 = match.group(1, 2, 3, 4)
            h2, m2, s2, ms2 = match.group(5, 6, 7, 8)
            text = match.group(9).replace('\n', ' ').strip()
            if not text:
                continue
            # 过滤掉纯音乐标记
            if (
                text.startswith("【")
                or text.startswith("[")
                or text.startswith("(")
                or text.startswith("（")
            ):
                continue
            start_ms = int(h1) * 3600000 + int(m1) * 60000 + int(s1) * 1000 + int(ms1)
            end_ms = int(h2) * 3600000 + int(m2) * 60000 + int(s2) * 1000 + int(ms2)
            segments.append({
                "start_ms": start_ms,
                "end_ms": end_ms,
                "text": text,
            })
        return segments

    def _transcribe_with_whisper(
        self,
        audio_path: str,
        language: str,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> list[dict]:
        """使用本地 Whisper.cpp 转录音频

        Args:
            audio_path: 音频文件路径（支持 mp3/wav/flac/ogg）
            language: 语言代码（ja/en）
            progress_callback: 进度回调

        Returns:
            list[dict]: 段落列表
        """
        whisper_cli = self._resolve_whisper_cli()
        if not os.path.isfile(whisper_cli):
            raise RuntimeError(f"未找到 Whisper.cpp 可执行文件: {whisper_cli}")

        model_path = self._resolve_whisper_model()
        if not os.path.isfile(model_path):
            raise RuntimeError(f"未找到 Whisper small 模型: {model_path}")

        if progress_callback:
            progress_callback(5, "启动 Whisper.cpp 本地识别...")

        with tempfile.TemporaryDirectory() as temp_dir:
            output_prefix = os.path.join(temp_dir, "whisper_result")
            cmd = [
                whisper_cli,
                "-m", model_path,
                "-f", audio_path,
                "-l", language,
                "--output-srt",
                "-of", output_prefix,
                "--no-prints",
            ]

            try:
                # 在 Windows 上避免弹出命令行窗口
                startupinfo = None
                if os.name == "nt":
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="ignore",
                    timeout=self.WHISPER_TIMEOUT,
                    startupinfo=startupinfo,
                )
            except subprocess.TimeoutExpired:
                raise RuntimeError(f"Whisper.cpp 识别超时（超过 {self.WHISPER_TIMEOUT // 60} 分钟）")
            except Exception as e:
                raise RuntimeError(f"Whisper.cpp 启动失败: {e}") from e

            if result.returncode != 0:
                stderr = result.stderr[-2000:] if result.stderr else ""
                raise RuntimeError(f"Whisper.cpp 识别失败 (code {result.returncode}): {stderr}")

            srt_path = output_prefix + ".srt"
            if not os.path.isfile(srt_path):
                raise RuntimeError(f"Whisper.cpp 未生成 SRT 文件: {srt_path}")

            if progress_callback:
                progress_callback(95, "解析识别结果...")

            with open(srt_path, "r", encoding="utf-8", errors="ignore") as f:
                srt_text = f.read()

            segments = self._parse_srt(srt_text)
            if not segments:
                raise RuntimeError("Whisper.cpp 识别结果为空")

            if progress_callback:
                progress_callback(100, f"识别完成，共 {len(segments)} 段")

            return segments

    def _transcribe_with_bcut(
        self,
        audio_path: str,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> list[dict]:
        """使用 BcutASR（必剪引擎）转录音频

        Args:
            audio_path: 音频文件路径
            progress_callback: 进度回调

        Returns:
            list[dict]: 段落列表
        """
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

        return segments

    def transcribe(
        self,
        audio_path: str,
        language: str = "ja",
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> list[dict]:
        """转录音频文件为带时间戳的文本段落

        Args:
            audio_path: 音频文件路径（支持 mp3/wav/flac/m4a）
            language: 语言代码
                - "zh": 中文，使用 BcutASR
                - "ja": 日语，使用 Whisper.cpp
                - "en": 英语，使用 Whisper.cpp
                默认为 "ja"（本项目主要面向日语歌曲场景）
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

        lang_lower = (language or "ja").lower()

        if lang_lower in ("ja", "en"):
            segments = self._transcribe_with_whisper(
                audio_path, lang_lower, progress_callback=progress_callback
            )
        elif lang_lower == "zh":
            segments = self._transcribe_with_bcut(
                audio_path, progress_callback=progress_callback
            )
        else:
            # 对于其他语言，默认使用 Whisper.cpp 尝试识别
            segments = self._transcribe_with_whisper(
                audio_path, lang_lower, progress_callback=progress_callback
            )

        # 再次校验转换后的结果
        if not segments:
            raise RuntimeError("转录结果为空，未获取到任何文本段落")

        return segments
