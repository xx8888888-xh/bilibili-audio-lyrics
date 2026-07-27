# -*- coding: utf-8 -*-
"""B站音频下载模块

通过WBI签名调用B站API获取DASH音频流，下载并转码为MP3格式（192kbps CBR，
兼容所有主流播放器和转录工具）。优先使用 ffmpeg 直接转码；当 ffmpeg 缺少音频编解码器时，
自动使用项目内置的 FlicFlac 工具包（faad + lame）进行解码和编码。
"""

import os
import re
import sys
import shutil
import time
import hashlib
import subprocess
from typing import Callable, Optional, Tuple
from urllib.parse import urlencode, quote

import requests


# WBI签名用的映射表（官方固定，勿改）
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49, 33, 9, 42,
    19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51,
    30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52
]

# 音频质量优先级列表：30280(192K) > 30232(132K) > 30216(64K)
AUDIO_QUALITY_PRIORITY = [30280, 30232, 30216]

# BV号正则：BV后跟10位字符（字母和数字）
BV_PATTERN = re.compile(r'BV[0-9A-Za-z]{10}')

# 文件名非法字符正则
ILLEGAL_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|]')

# 基础请求头
BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/109.0",
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.8",
}


def _get_mixin_key(orig: str) -> str:
    """根据映射表重排原始key，取前32位得到mixin_key

    Args:
        orig: img_key + sub_key 拼接后的字符串（长度64）

    Returns:
        重排后取前32位的 mixin_key
    """
    return ''.join(orig[i] for i in MIXIN_KEY_ENC_TAB)[:32]


def _build_wbi_params(params: dict, img_key: str, sub_key: str) -> dict:
    """对请求参数进行WBI签名，返回包含 wts 和 w_rid 的完整参数字典

    Args:
        params: 原始请求参数
        img_key: 从nav接口获取的img_key
        sub_key: 从nav接口获取的sub_key

    Returns:
        添加了 wts 和 w_rid 的参数字典
    """
    mixin_key = _get_mixin_key(img_key + sub_key)
    # 复制参数并添加时间戳
    signed = dict(params)
    signed['wts'] = int(time.time())
    # 过滤value中的特殊字符（WBI要求）
    signed = {
        k: ''.join(c for c in str(v) if c not in "!'()*")
        for k, v in signed.items()
    }
    # 按key字典序排序，用quote编码（空格->%20，而非+）
    query = urlencode(sorted(signed.items()), quote_via=quote)
    # 计算w_rid
    w_rid = hashlib.md5((query + mixin_key).encode('utf-8')).hexdigest()
    signed['w_rid'] = w_rid
    return signed


class BilibiliAudioDownloader:
    """B站音频下载器

    通过WBI签名调用B站API获取DASH音频流，下载并转码为MP3格式（192kbps CBR）。
    优先使用 ffmpeg 直接转码；当 ffmpeg 缺少音频编解码器时，
    自动使用项目内置的 FlicFlac 工具包（faad + lame）。
    """

    def __init__(self, sessdata: str = None):
        """初始化下载器

        Args:
            sessdata: 可选的B站登录凭证SESSDATA，未登录时传None
        """
        self.sessdata = sessdata
        self.session = requests.Session()
        # 禁用环境代理设置（避免错误的代理环境变量导致请求失败）
        self.session.trust_env = False
        # 设置基础请求头
        self.session.headers.update(BASE_HEADERS)
        if sessdata:
            self.session.cookies.set("SESSDATA", sessdata, domain=".bilibili.com")
        # 缓存WBI keys，避免重复请求nav接口
        self._wbi_keys: Optional[Tuple[str, str]] = None
        # 初始化buvid3/buvid4 cookie，规避B站412风控
        self._buvid_initialized = False

    def _ensure_buvid(self) -> None:
        """获取buvid3/buvid4 cookie，规避B站412风控（仅需获取一次）"""
        if self._buvid_initialized:
            return
        try:
            resp = self.session.get(
                "https://api.bilibili.com/x/frontend/finger/spi", timeout=10
            )
            data = resp.json()
            if data.get('code') == 0:
                b3 = data['data']['b_3']
                b4 = data['data']['b_4']
                self.session.cookies.set('buvid3', b3, domain='.bilibili.com')
                self.session.cookies.set('buvid4', b4, domain='.bilibili.com')
        except Exception:
            pass  # 获取失败不阻塞，部分接口仍可正常调用
        self._buvid_initialized = True

    def _get_headers(self, bvid: str = None) -> dict:
        """获取请求头（含Referer）

        Args:
            bvid: BV号，用于构造Referer

        Returns:
            请求头字典
        """
        headers = {"Origin": "https://www.bilibili.com"}
        if bvid:
            headers["Referer"] = f"https://www.bilibili.com/video/{bvid}"
        return headers

    def _request_with_retry(self, url: str, params=None, headers=None,
                            max_retries: int = 3) -> dict:
        """带重试的GET请求

        Args:
            url: 请求URL
            params: 请求参数
            headers: 额外请求头
            max_retries: 最大重试次数

        Returns:
            JSON响应字典（data字段已存在的JSON）

        Raises:
            RuntimeError: API返回错误或网络请求失败
        """
        last_error = None
        for attempt in range(max_retries):
            try:
                resp = self.session.get(url, params=params, headers=headers, timeout=15)
                resp.raise_for_status()
                data = resp.json()
                if data.get('code') != 0:
                    raise RuntimeError(
                        f"B站API错误: code={data.get('code')}, message={data.get('message')}"
                    )
                return data
            except RuntimeError:
                # API错误不重试
                raise
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    time.sleep(1 * (attempt + 1))
        raise RuntimeError(f"网络请求失败（已重试{max_retries}次）: {last_error}")

    def parse_url(self, url: str) -> Tuple[str, int]:
        """解析B站视频URL，返回BV号和分P序号

        支持：
        - https://www.bilibili.com/video/BV1xx411c7mD
        - https://www.bilibili.com/video/BV1xx411c7mD?p=2 （分P）
        - https://b23.tv/xxx 短链（需HTTP重定向获取真实URL）
        - 纯BV号如 BV1xx411c7mD

        Args:
            url: B站视频URL

        Returns:
            (bvid, page) 元组，page为分P序号（从1开始，默认1）

        Raises:
            ValueError: URL格式无效
        """
        url = url.strip()
        page = 1

        # 处理b23.tv短链：跟随重定向获取真实URL
        if 'b23.tv' in url:
            try:
                resp = self.session.get(url, allow_redirects=True, timeout=10)
                url = resp.url
            except Exception as e:
                raise ValueError(f"短链解析失败: {e}")

        # 提取分P参数
        p_match = re.search(r'[?&]p=(\d+)', url)
        if p_match:
            page = int(p_match.group(1))

        # 提取BV号
        match = BV_PATTERN.search(url)
        if not match:
            raise ValueError(f"无法从URL中提取BV号: {url}")
        return match.group(0), page

    def _get_wbi_keys(self) -> Tuple[str, str]:
        """获取WBI签名的img_key和sub_key（带缓存）

        nav接口在未登录时返回code=-101，但wbi_img字段仍然可用。

        Returns:
            (img_key, sub_key)
        """
        if self._wbi_keys:
            return self._wbi_keys
        # nav接口未登录时code=-101但wbi_img仍存在，不能使用_request_with_retry
        last_error = None
        for attempt in range(3):
            try:
                resp = self.session.get(
                    "https://api.bilibili.com/x/web-interface/nav", timeout=15
                )
                resp.raise_for_status()
                data = resp.json()
                wbi_img = data.get('data', {}).get('wbi_img', {})
                img_url = wbi_img.get('img_url', '')
                sub_url = wbi_img.get('sub_url', '')
                if not img_url or not sub_url:
                    raise RuntimeError(f"nav接口未返回wbi_img: code={data.get('code')}")
                # 从URL中提取文件名作为key
                img_key = img_url.rsplit('/', 1)[1].split('.')[0]
                sub_key = sub_url.rsplit('/', 1)[1].split('.')[0]
                self._wbi_keys = (img_key, sub_key)
                return self._wbi_keys
            except RuntimeError:
                raise
            except Exception as e:
                last_error = e
                if attempt < 2:
                    time.sleep(1 * (attempt + 1))
        raise RuntimeError(f"获取WBI keys失败（已重试3次）: {last_error}")

    def _get_cid(self, bvid: str, page: int = 1) -> Tuple[str, str]:
        """获取视频CID和分P标题

        Args:
            bvid: BV号
            page: 分P序号（从1开始）

        Returns:
            (cid, part_title) 元组

        Raises:
            RuntimeError: 未找到分P信息或分P序号超出范围
        """
        data = self._request_with_retry(
            "https://api.bilibili.com/x/player/pagelist",
            params={"bvid": bvid, "jsonp": "jsonp"},
            headers=self._get_headers(bvid),
        )
        pages = data['data']
        if not pages:
            raise RuntimeError("未找到视频分P信息")
        idx = page - 1
        if idx < 0 or idx >= len(pages):
            raise RuntimeError(f"分P序号{page}超出范围（共{len(pages)}P）")
        p = pages[idx]
        return str(p['cid']), p.get('part', '')

    def _get_title(self, bvid: str) -> str:
        """获取视频标题

        Args:
            bvid: BV号

        Returns:
            视频标题
        """
        data = self._request_with_retry(
            "https://api.bilibili.com/x/web-interface/view",
            params={"bvid": bvid},
            headers=self._get_headers(bvid),
        )
        return data['data']['title']

    def _get_playurl(self, bvid: str, cid: str) -> dict:
        """获取DASH播放地址（需WBI签名）

        Args:
            bvid: BV号
            cid: 视频CID

        Returns:
            播放地址数据（data字段内容）

        Raises:
            RuntimeError: 获取失败
        """
        img_key, sub_key = self._get_wbi_keys()
        params = {
            "cid": cid,
            "bvid": bvid,
            "qn": 80,
            "type": "",
            "otype": "json",
            "fnver": 0,
            "fnval": 4048,
            "fourk": 1,
            "from_client": "BROWSER",
            "is_main_page": "true",
            "need_fragment": "false",
            "isGaiaAvoided": "false",
            "client_attr": 0,
            "session": "",
            "voice_balance": 1,
            "web_location": 1315873,
        }
        # 未登录时追加try_look=1
        if not self.sessdata:
            params["try_look"] = 1
        # WBI签名
        signed_params = _build_wbi_params(params, img_key, sub_key)
        data = self._request_with_retry(
            "https://api.bilibili.com/x/player/wbi/playurl",
            params=signed_params,
            headers=self._get_headers(bvid),
        )
        return data['data']

    def _select_audio(self, playurl_data: dict) -> dict:
        """根据优先级选择音频流

        优先级：30280(192K) > 30232(132K) > 30216(64K)

        Args:
            playurl_data: 播放地址数据

        Returns:
            选中的音频流信息字典

        Raises:
            RuntimeError: 未找到音频流
        """
        audio_list = playurl_data.get('dash', {}).get('audio', [])
        if not audio_list:
            raise RuntimeError("未找到DASH音频流")
        audio_map = {a['id']: a for a in audio_list}
        for qid in AUDIO_QUALITY_PRIORITY:
            if qid in audio_map:
                return audio_map[qid]
        # 都没匹配，返回第一个
        return audio_list[0]

    def _download_audio_stream(self, audio: dict, output_path: str, bvid: str,
                               progress_callback: Callable[[int, str], None] = None) -> None:
        """下载音频流到文件

        Args:
            audio: 音频流信息字典
            output_path: 输出文件路径（.m4s）
            bvid: BV号（用于Referer）
            progress_callback: 进度回调，映射到30-90区间

        Raises:
            RuntimeError: 下载失败
        """
        # 优先使用baseUrl，兼容base_url
        url = audio.get('baseUrl') or audio.get('base_url')
        if not url:
            raise RuntimeError("音频流URL为空")

        # 下载音频流必须带Referer和User-Agent，否则403
        headers = {
            "User-Agent": BASE_HEADERS["User-Agent"],
            "Referer": f"https://www.bilibili.com/video/{bvid}",
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.8",
            "Origin": "https://www.bilibili.com",
        }

        last_error = None
        for attempt in range(3):
            try:
                resp = self.session.get(url, headers=headers, stream=True, timeout=30)
                resp.raise_for_status()
                total = int(resp.headers.get('Content-Length', 0))
                downloaded = 0
                with open(output_path, 'wb') as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if progress_callback and total > 0:
                                # 下载进度映射到 30-90 区间
                                progress = 30 + int(downloaded / total * 60)
                                progress_callback(
                                    min(progress, 90),
                                    f"下载音频中 {downloaded // 1024}KB / {total // 1024}KB"
                                )
                return
            except Exception as e:
                last_error = e
                if attempt < 2:
                    time.sleep(1 * (attempt + 1))
        raise RuntimeError(f"音频流下载失败（已重试3次）: {last_error}")

    @staticmethod
    def _resolve_flicflac_tool(tool_name: str) -> str:
        """解析项目内置的 FlicFlac 工具路径

        优先级：
        1. PyInstaller 打包环境：sys._MEIPASS/FlicFlac-master/<tool>.exe
        2. 开发环境：项目根目录下的 FlicFlac-master/<tool>.exe

        Args:
            tool_name: 工具名（如 faad、lame，不带 .exe）

        Returns:
            工具的绝对路径
        """
        exe_name = f"{tool_name}.exe"
        if hasattr(sys, '_MEIPASS'):
            packed_path = os.path.join(sys._MEIPASS, "FlicFlac-master", exe_name)
            if os.path.isfile(packed_path):
                return packed_path

        dev_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "FlicFlac-master", exe_name
        )
        return dev_path

    def _m4a_to_mp3(self, m4a_path: str, mp3_path: str) -> None:
        """使用 FlicFlac 的 faad + lame 将 m4a 转为 mp3"""
        faad_path = self._resolve_flicflac_tool("faad")
        lame_path = self._resolve_flicflac_tool("lame")
        if not os.path.isfile(faad_path):
            raise RuntimeError(f"项目内置的 faad.exe 不存在: {faad_path}")
        if not os.path.isfile(lame_path):
            raise RuntimeError(f"项目内置的 lame.exe 不存在: {lame_path}")

        temp_wav = mp3_path + ".tmp.wav"
        try:
            # faad: m4a -> wav
            cmd = [faad_path, "-q", "-o", temp_wav, m4a_path]
            result = subprocess.run(cmd, capture_output=True, timeout=180)
            if result.returncode != 0:
                stderr = result.stderr.decode('utf-8', errors='ignore')
                raise RuntimeError(f"faad 解码失败: {stderr}")

            # lame: wav -> mp3 (192kbps CBR)
            cmd = [lame_path, "-q", "2", "-b", "192", temp_wav, mp3_path]
            result = subprocess.run(cmd, capture_output=True, timeout=180)
            if result.returncode != 0:
                stderr = result.stderr.decode('utf-8', errors='ignore')
                raise RuntimeError(f"lame 编码失败: {stderr}")
        finally:
            try:
                os.remove(temp_wav)
            except OSError:
                pass

    def _convert_to_mp3(self, input_path: str, output_path: str) -> None:
        """将下载的m4s音频流转码为MP3格式

        优先使用 ffmpeg 直接 m4s -> mp3；
        当 ffmpeg 缺少音频编解码器时，先使用 ffmpeg 将 m4s 无损封装为 m4a，
        再调用项目内置的 FlicFlac（faad + lame）转码为 MP3（192kbps CBR）。

        Args:
            input_path: 输入m4s文件路径
            output_path: 输出mp3文件路径

        Raises:
            RuntimeError: 转码失败或没有任何可用解码器
        """
        # 1. 优先尝试 ffmpeg 直接 m4s -> mp3
        if shutil.which("ffmpeg"):
            cmd = [
                "ffmpeg", "-y",
                "-i", input_path,
                "-vn",
                "-c:a", "libmp3lame",
                "-b:a", "192k",
                output_path
            ]
            try:
                result = subprocess.run(cmd, capture_output=True, timeout=120)
            except FileNotFoundError:
                pass
            except subprocess.TimeoutExpired:
                raise RuntimeError("ffmpeg 转码超时")
            else:
                if result.returncode == 0:
                    return
                # 直接 mp3 失败，尝试 ffmpeg 仅做 m4s -> m4a 封装（-c:a copy 不需要编解码器）
                stderr = result.stderr.decode('utf-8', errors='ignore')
                temp_m4a = output_path + ".tmp.mp4"
                try:
                    cmd = [
                        "ffmpeg", "-y",
                        "-i", input_path,
                        "-vn",
                        "-c:a", "copy",
                        "-f", "mp4",
                        temp_m4a
                    ]
                    result2 = subprocess.run(cmd, capture_output=True, timeout=120)
                    if result2.returncode == 0:
                        self._m4a_to_mp3(temp_m4a, output_path)
                        return
                    stderr2 = result2.stderr.decode('utf-8', errors='ignore')
                    raise RuntimeError(
                        f"ffmpeg 直接转 mp3 失败: {stderr}\n"
                        f"ffmpeg 封装 m4a 也失败: {stderr2}"
                    )
                finally:
                    try:
                        os.remove(temp_m4a)
                    except OSError:
                        pass

        # 2. 无 ffmpeg 时，尝试直接用 FlicFlac/faad 解码 m4s（部分 m4s 可被识别）
        faad_path = self._resolve_flicflac_tool("faad")
        lame_path = self._resolve_flicflac_tool("lame")
        if os.path.isfile(faad_path) and os.path.isfile(lame_path):
            temp_wav = output_path + ".tmp.wav"
            try:
                cmd = [faad_path, "-q", "-o", temp_wav, input_path]
                result = subprocess.run(cmd, capture_output=True, timeout=180)
                if result.returncode == 0:
                    cmd = [lame_path, "-q", "2", "-b", "192", temp_wav, output_path]
                    result2 = subprocess.run(cmd, capture_output=True, timeout=180)
                    if result2.returncode == 0:
                        return
                    stderr2 = result2.stderr.decode('utf-8', errors='ignore')
                    raise RuntimeError(f"lame 编码失败: {stderr2}")
                stderr = result.stderr.decode('utf-8', errors='ignore')
                raise RuntimeError(
                    f"faad 解码失败（无 ffmpeg 时无法预封装 m4s）: {stderr}"
                )
            finally:
                try:
                    os.remove(temp_wav)
                except OSError:
                    pass

        raise RuntimeError(
            "未找到可用的 ffmpeg 或项目内置的 FlicFlac 工具包（faad.exe + lame.exe）。"
        )

    def _sanitize_filename(self, name: str) -> str:
        """去除文件名中的非法字符（替换为下划线）

        Args:
            name: 原始文件名

        Returns:
            安全的文件名
        """
        return ILLEGAL_FILENAME_CHARS.sub('_', name).strip()

    def download(self, url: str, output_dir: str,
                 progress_callback: Callable[[int, str], None] = None) -> dict:
        """下载B站视频的音频流

        Args:
            url: B站视频URL（支持完整URL、b23.tv短链、纯BV号）
            output_dir: 输出目录
            progress_callback: 进度回调函数 callback(progress: int, message: str)，
                              progress为0-100

        Returns:
            dict: {
                "audio_path": str,  # 下载的音频文件完整路径（.mp3格式）
                "title": str,       # 视频标题
                "bvid": str,        # BV号
                "cid": str,         # 视频CID
            }

        Raises:
            ValueError: URL格式无效
            RuntimeError: 下载失败（API错误、网络错误等）
        """
        def _progress(p: int, msg: str):
            if progress_callback:
                progress_callback(p, msg)

        # ========== 0-10%: 解析URL和获取视频信息 ==========
        _progress(0, "解析URL...")
        bvid, page = self.parse_url(url)
        _progress(3, f"BV号: {bvid}")

        # 初始化buvid cookie，规避412风控
        self._ensure_buvid()

        _progress(5, "获取视频CID...")
        cid, part_title = self._get_cid(bvid, page)
        _progress(7, f"CID: {cid}")

        _progress(9, "获取视频标题...")
        title = self._get_title(bvid)
        _progress(10, f"标题: {title}")

        # ========== 10-30%: 获取音频流URL ==========
        _progress(15, "获取音频流URL（WBI签名）...")
        playurl_data = self._get_playurl(bvid, cid)
        _progress(25, "选择音频流...")
        audio = self._select_audio(playurl_data)
        _progress(30, f"已选择音频流: id={audio['id']}")

        # ========== 30-90%: 下载音频 ==========
        os.makedirs(output_dir, exist_ok=True)
        safe_title = self._sanitize_filename(title)
        temp_m4s = os.path.join(output_dir, f"{safe_title}.m4s")
        output_mp3 = os.path.join(output_dir, f"{safe_title}.mp3")

        _progress(30, "开始下载音频...")
        self._download_audio_stream(audio, temp_m4s, bvid, progress_callback)
        _progress(90, "音频下载完成")

        # ========== 90-100%: 转码为MP3 ==========
        _progress(92, "转码为MP3中...")
        self._convert_to_mp3(temp_m4s, output_mp3)
        # 删除临时m4s文件
        try:
            os.remove(temp_m4s)
        except OSError:
            pass
        _progress(100, f"完成: {output_mp3}")

        return {
            "audio_path": output_mp3,
            "title": title,
            "bvid": bvid,
            "cid": cid,
        }
