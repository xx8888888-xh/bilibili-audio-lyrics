# -*- coding: utf-8 -*-
"""PyInstaller 打包配置"""

import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# 收集 VideoCaptioner 的所有数据文件和子模块
vc_path = os.path.join(os.getcwd(), "VideoCaptioner-master")
# 收集 FlicFlac 工具包（无 ffmpeg 时用作 WAV 解码回退）
flicflac_path = os.path.join(os.getcwd(), "FlicFlac-master")
# 收集 Whisper.cpp 运行时（含 DLL）和 small 模型
whisper_path = os.path.join(os.getcwd(), "whisper_test", "Release")
model_path = os.path.join(os.getcwd(), "models")

datas = []
# 添加 VideoCaptioner 整个目录作为数据文件
datas.append((vc_path, "VideoCaptioner-master"))
# 添加 FlicFlac 工具包作为数据文件
datas.append((flicflac_path, "FlicFlac-master"))
# 添加 Whisper.cpp 运行时目录作为数据文件
datas.append((whisper_path, os.path.join("whisper_test", "Release")))
# 添加 Whisper small 模型作为数据文件
datas.append((model_path, "models"))

# 收集 videocaptioner 包的数据文件（如果有）
datas += collect_data_files("videocaptioner")

# 收集必要的隐藏导入
hiddenimports = []
hiddenimports += collect_submodules("videocaptioner")
# pydub 依赖
hiddenimports += ["pydub", "pydub.utils", "pydub.audio_segment"]
# 其他可能的隐藏导入
hiddenimports += ["diskcache", "langdetect", "langdetect.detector_factory"]

a = Analysis(
    ["main.py"],
    pathex=[os.getcwd()],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除不需要的大型模块以减小体积
        "matplotlib", "numpy", "scipy", "pandas",
        "PyQt5.QtWebEngineCore", "PyQt5.QtWebEngineWidgets",
        "PyQt5.QtWebChannel", "PyQt5.QtMultimedia",
        "PyQt5.QtMultimediaWidgets", "PyQt5.QtSql",
        "PyQt5.QtTest", "PyQt5.QtBluetooth",
        "PyQt5.QtNetwork", "PyQt5.QtPositioning",
        "PyQt5.QtSensors", "PyQt5.QtSerialPort",
        "PyQt5.QtSvg", "PyQt5.QtXml",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="BilibiliAudioLyrics",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
