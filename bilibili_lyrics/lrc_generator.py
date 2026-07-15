"""LRC歌词文件生成模块

将带时间戳的文本段落列表转换为标准LRC歌词文件。
纯Python标准库实现，不依赖任何外部库或其他项目模块。
"""


def _format_timestamp(total_ms: int, ms_digits: int) -> str:
    """将毫秒时间戳格式化为LRC时间标签

    Args:
        total_ms: 总毫秒数（已应用偏移，可能为负，将钳制为0）
        ms_digits: 毫秒位数，2=[mm:ss.xx]，3=[mm:ss.xxx]

    Returns:
        str: 格式化的时间标签，如 [01:23.45] 或 [01:23.456]
    """
    # 钳制负数为0
    if total_ms < 0:
        total_ms = 0

    minutes = total_ms // 60000
    remaining_ms = total_ms % 60000
    seconds = remaining_ms // 1000
    ms_part = remaining_ms % 1000

    if ms_digits == 2:
        # 2位模式：百分秒，四舍五入
        centiseconds = (ms_part + 5) // 10
        if centiseconds >= 100:
            centiseconds = 99
        return f"[{minutes:02d}:{seconds:02d}.{centiseconds:02d}]"
    else:
        # 3位模式：毫秒
        return f"[{minutes:02d}:{seconds:02d}.{ms_part:03d}]"


def generate_lrc(
    segments: list[dict],
    output_path: str,
    metadata: dict = None,
    ms_digits: int = 2,
) -> str:
    """从带时间戳的段落列表生成LRC歌词文件

    Args:
        segments: 段落列表，每个段落数据包含：
            - start_ms: 起始时间（毫秒，整数）
            - end_ms: 结束时间（毫秒，整数，LRC不使用但必须接受）
            - text: 歌词文本（字符串）
        output_path: 输出LRC文件路径
        metadata: 元数据字典，可选键：
            - title: 歌曲标题
            - artist: 歌手
            - album: 专辑
            - by: LRC制作人
            - offset: 时间偏移（毫秒，正=提前，负=延后）
        ms_digits: 时间戳毫秒位数，2=[mm:ss.xx]（标准格式，最大兼容性），3=[mm:ss.xxx]（现代格式）

    Returns:
        str: 生成的LRC文件内容字符串（同时写入文件）
    """
    # 处理metadata为None的情况
    if metadata is None:
        metadata = {}

    # 获取时间偏移（毫秒），默认为0
    offset = metadata.get("offset", 0)
    if offset is None:
        offset = 0

    lines: list[str] = []

    # 元数据标签映射：LRC标签名 -> metadata键名
    metadata_map = [
        ("ti", "title"),
        ("ar", "artist"),
        ("al", "album"),
        ("by", "by"),
    ]

    # 写入元数据标签（跳过不存在的键或空值）
    for tag, key in metadata_map:
        value = metadata.get(key)
        if value is not None and str(value).strip() != "":
            lines.append(f"[{tag}:{value}]")

    # 写入offset标签（仅当偏移值非0时）
    if offset != 0:
        lines.append(f"[offset:{offset}]")

    # 写入歌词行
    for segment in segments:
        text = segment.get("text", "")
        # 跳过空文本行（text为空或仅空白字符）
        if not text or not str(text).strip():
            continue

        start_ms = segment.get("start_ms", 0)
        # 应用时间偏移
        total_ms = start_ms + offset
        # 格式化时间标签
        timestamp = _format_timestamp(total_ms, ms_digits)
        # 时间标签后直接跟歌词文本，无空格
        lines.append(f"{timestamp}{text}")

    # 拼接内容：LF换行符，文件末尾保留一个换行符
    content = "\n".join(lines) + "\n"

    # 写入文件：UTF-8编码（无BOM），LF换行符
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        f.write(content)

    return content
