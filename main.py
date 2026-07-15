# -*- coding: utf-8 -*-
"""B站音频歌词生成器 - 程序入口"""

import sys
import os

# 确保项目目录在sys.path中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFont
from bilibili_lyrics.gui import MainWindow


def main() -> None:
    """程序入口"""
    app = QApplication(sys.argv)
    # 设置全局字体：微软雅黑 10pt
    app.setFont(QFont("微软雅黑", 10))
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
