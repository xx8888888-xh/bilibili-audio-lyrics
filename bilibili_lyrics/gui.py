# -*- coding: utf-8 -*-
"""B站音频歌词生成器 - GUI主窗口模块

支持多链接批量处理（并行下载+转录+生成歌词）。
依赖模块：
    - bilibili_downloader.BilibiliAudioDownloader
    - transcriber.AudioTranscriber
    - lrc_generator.generate_lrc
"""

import os
import sys
from datetime import datetime
from typing import Optional

from PyQt5.QtCore import QObject, QThread, pyqtSignal, Qt
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTextEdit, QProgressBar, QFileDialog,
    QMessageBox, QFrame, QCheckBox, QSpinBox,
)


class WorkerSignals(QObject):
    """单个任务工作线程信号定义（用于线程安全的UI更新）"""

    progress = pyqtSignal(int, str)       # progress%, message
    finished = pyqtSignal(str, str)       # url, output_path
    error = pyqtSignal(str, str)          # url, error_message
    log = pyqtSignal(str)                 # log_message


class SingleUrlWorker(QThread):
    """单个URL的歌词生成工作线程：下载→转录→生成歌词"""

    def __init__(self, url: str, output_dir: str, auto_open: bool = False):
        super().__init__()
        self.url: str = url
        self.output_dir: str = output_dir
        self.auto_open: bool = auto_open
        self.signals = WorkerSignals()

    def run(self) -> None:
        """执行单个URL的工作流程"""
        try:
            os.makedirs(self.output_dir, exist_ok=True)

            # 懒加载依赖模块（在子线程中导入，避免主线程阻塞）
            from bilibili_lyrics.bilibili_downloader import BilibiliAudioDownloader
            from bilibili_lyrics.transcriber import AudioTranscriber
            from bilibili_lyrics.lrc_generator import generate_lrc

            # 步骤1: 下载音频 (进度 0-40%)
            self.signals.log.emit(f"[{self.url}] 开始下载音频...")
            downloader = BilibiliAudioDownloader()
            result = downloader.download(
                self.url, self.output_dir,
                progress_callback=lambda p, m: self.signals.progress.emit(
                    int(p * 0.4), f"下载: {m}")
            )
            audio_path: str = result["audio_path"]
            title: str = result["title"]
            self.signals.log.emit(f"[{self.url}] 下载完成: {os.path.basename(audio_path)}")

            # 步骤2: 转录音频 (进度 40-90%)
            self.signals.log.emit(f"[{self.url}] 开始转录音频...")
            transcriber = AudioTranscriber()
            segments = transcriber.transcribe(
                audio_path,
                progress_callback=lambda p, m: self.signals.progress.emit(
                    int(40 + p * 0.5), f"转录: {m}")
            )
            self.signals.log.emit(f"[{self.url}] 转录完成，共 {len(segments)} 段")

            # 步骤3: 生成歌词 (进度 90-100%)
            self.signals.log.emit(f"[{self.url}] 正在生成LRC歌词文件...")
            # 文件名安全化
            safe_title = "".join(
                c if c not in r'\/:*?"<>|' else "_" for c in title
            )
            lrc_path = os.path.join(self.output_dir, f"{safe_title}.lrc")
            generate_lrc(
                segments, lrc_path,
                metadata={"title": title, "by": "B站歌词生成器"},
            )
            self.signals.log.emit(f"[{self.url}] 歌词已保存: {lrc_path}")

            self.signals.progress.emit(100, "完成")
            self.signals.finished.emit(self.url, lrc_path)

        except Exception as e:
            self.signals.error.emit(self.url, f"{type(e).__name__}: {e}")


class MainWindow(QMainWindow):
    """主窗口 - 支持多链接批量处理"""

    def __init__(self):
        super().__init__()
        self.workers = []  # 所有活跃的工作线程
        self.total_tasks = 0
        self.completed_tasks = 0
        self.failed_tasks = 0
        self._init_ui()
        self._init_style()

    # ---------- UI 初始化 ----------

    def _init_ui(self) -> None:
        """初始化界面布局"""
        self.setWindowTitle("B站音频歌词生成器 - 批量版")
        self.setFixedSize(700, 650)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        # 标题
        title_label = QLabel("B站音频歌词生成器")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setObjectName("titleLabel")
        layout.addWidget(title_label)

        subtitle_label = QLabel("支持批量多链接处理，每行输入一个B站视频链接")
        subtitle_label.setAlignment(Qt.AlignCenter)
        subtitle_label.setObjectName("subtitleLabel")
        layout.addWidget(subtitle_label)

        layout.addWidget(self._make_separator())

        # B站视频链接（多行输入）
        url_label = QLabel("B站视频链接（每行一个，支持批量）：")
        layout.addWidget(url_label)
        self.url_input = QTextEdit()
        self.url_input.setPlaceholderText(
            "请输入B站视频链接，每行一个，例如：\n"
            "https://www.bilibili.com/video/BVxxxxx\n"
            "https://www.bilibili.com/video/BVyyyyy\n"
            "https://b23.tv/xxxxxxx"
        )
        self.url_input.setMinimumHeight(100)
        layout.addWidget(self.url_input)

        # 输出目录
        dir_row = QHBoxLayout()
        dir_label = QLabel("输出目录:")
        dir_label.setMinimumWidth(80)
        self.dir_input = QLineEdit()
        self.dir_input.setPlaceholderText("选择输出目录")
        self.dir_input.setText(os.path.join(os.getcwd(), "output"))
        self.browse_btn = QPushButton("浏览")
        self.browse_btn.clicked.connect(self._browse_dir)
        dir_row.addWidget(dir_label)
        dir_row.addWidget(self.dir_input, 1)
        dir_row.addWidget(self.browse_btn)
        layout.addLayout(dir_row)

        # 选项行：并行数量 + 自动打开
        opt_row = QHBoxLayout()
        opt_row.addWidget(QLabel("并行任务数:"))
        self.parallel_spin = QSpinBox()
        self.parallel_spin.setMinimum(1)
        self.parallel_spin.setMaximum(5)
        self.parallel_spin.setValue(2)
        self.parallel_spin.setToolTip("同时处理的链接数量（建议2-3，过高可能触发B站风控）")
        opt_row.addWidget(self.parallel_spin)
        opt_row.addStretch()
        self.auto_open_chk = QCheckBox("完成后自动打开输出目录")
        self.auto_open_chk.setChecked(True)
        opt_row.addWidget(self.auto_open_chk)
        layout.addLayout(opt_row)

        # 开始按钮
        self.start_btn = QPushButton("开始生成歌词")
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.clicked.connect(self._start)
        layout.addWidget(self.start_btn)

        layout.addWidget(self._make_separator())

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")
        layout.addWidget(self.progress_bar)

        # 状态标签
        self.status_label = QLabel("状态: 就绪")
        layout.addWidget(self.status_label)

        layout.addWidget(self._make_separator())

        # 日志区域
        layout.addWidget(QLabel("日志:"))
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text, 1)

    def _make_separator(self) -> QFrame:
        """创建水平分隔线"""
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        return sep

    def _init_style(self) -> None:
        """初始化样式（蓝色主题、现代简洁风格）"""
        self.setStyleSheet("""
            QMainWindow { background-color: #f5f6fa; }
            QLabel { color: #2c3e50; font-size: 10pt; }
            QLabel#titleLabel {
                font-size: 18pt; font-weight: bold; color: #2c3e50;
            }
            QLabel#subtitleLabel {
                font-size: 9pt; color: #7f8c8d;
            }
            QLineEdit {
                padding: 6px; border: 1px solid #dcdde1;
                border-radius: 4px; font-size: 10pt;
                background-color: #ffffff; selection-background-color: #3498db;
            }
            QLineEdit:focus { border: 1px solid #3498db; }
            QTextEdit {
                padding: 6px; border: 1px solid #dcdde1;
                border-radius: 4px; font-size: 10pt;
                background-color: #ffffff; selection-background-color: #3498db;
            }
            QTextEdit:focus { border: 1px solid #3498db; }
            QPushButton {
                padding: 8px 16px; border: none; border-radius: 4px;
                font-size: 10pt; color: #ffffff; background-color: #3498db;
            }
            QPushButton:hover { background-color: #2980b9; }
            QPushButton:pressed { background-color: #2471a3; }
            QPushButton:disabled { background-color: #bdc3c7; }
            QCheckBox { color: #2c3e50; font-size: 10pt; }
            QSpinBox {
                padding: 4px; border: 1px solid #dcdde1;
                border-radius: 4px; font-size: 10pt;
                background-color: #ffffff;
            }
            QProgressBar {
                border: 1px solid #dcdde1; border-radius: 4px;
                text-align: center; background-color: #ffffff;
                min-height: 20px; font-size: 9pt; color: #2c3e50;
            }
            QProgressBar::chunk { background-color: #3498db; border-radius: 3px; }
        """)

    # ---------- 槽函数 ----------

    def _browse_dir(self) -> None:
        """浏览选择输出目录"""
        start_dir = self.dir_input.text() or os.getcwd()
        dir_path = QFileDialog.getExistingDirectory(self, "选择输出目录", start_dir)
        if dir_path:
            self.dir_input.setText(dir_path)

    def _parse_urls(self) -> list:
        """从输入框解析URL列表（每行一个，过滤空行和注释）"""
        text = self.url_input.toPlainText()
        urls = []
        for line in text.split("\n"):
            url = line.strip()
            if url and not url.startswith("#"):
                urls.append(url)
        return urls

    def _start(self) -> None:
        """开始批量生成歌词"""
        urls = self._parse_urls()
        output_dir = self.dir_input.text().strip()

        # 输入校验
        if not urls:
            QMessageBox.warning(self, "提示", "请输入至少一个B站视频链接")
            return
        if not output_dir:
            QMessageBox.warning(self, "提示", "请选择输出目录")
            return

        # 重置状态
        self.workers.clear()
        self.total_tasks = len(urls)
        self.completed_tasks = 0
        self.failed_tasks = 0
        self.progress_bar.setValue(0)
        self.status_label.setText(f"状态: 正在处理 0/{self.total_tasks}...")
        self.log_text.clear()
        self.start_btn.setEnabled(False)

        self._log(f"开始批量处理，共 {self.total_tasks} 个链接，并行数 {self.parallel_spin.value()}")
        self._log(f"输出目录: {output_dir}")
        self._log("-" * 50)

        # 启动任务调度
        self._pending_urls = list(urls)
        self._output_dir = output_dir
        self._max_parallel = self.parallel_spin.value()
        self._schedule_next()

    def _schedule_next(self) -> None:
        """调度下一个待处理的URL（控制并行数量）"""
        # 清理已完成的worker
        self.workers = [w for w in self.workers if w.isRunning()]

        # 检查是否全部完成
        active_count = len(self.workers)
        remaining = len(self._pending_urls) if hasattr(self, '_pending_urls') else 0

        if remaining == 0 and active_count == 0:
            self._on_all_finished()
            return

        # 启动新任务直到达到并行上限
        while active_count < self._max_parallel and self._pending_urls:
            url = self._pending_urls.pop(0)
            worker = SingleUrlWorker(url, self._output_dir, auto_open=False)
            worker.signals.progress.connect(self._on_task_progress)
            worker.signals.finished.connect(self._on_task_finished)
            worker.signals.error.connect(self._on_task_error)
            worker.signals.log.connect(self._log)
            self.workers.append(worker)
            worker.start()
            active_count += 1
            self._log(f"[{url}] 任务已启动")

    def _on_task_progress(self, progress: int, message: str) -> None:
        """单个任务进度更新"""
        # 总进度 = (已完成任务数 / 总任务数) * 100 + (当前进度 / 总任务数)
        # 简化：显示已完成比例
        base = (self.completed_tasks / self.total_tasks) * 100 if self.total_tasks else 0
        current = (progress / self.total_tasks) if self.total_tasks else 0
        total = int(base + current)
        self.progress_bar.setValue(min(total, 99))
        self.status_label.setText(
            f"状态: {message} (已完成 {self.completed_tasks}/{self.total_tasks})")

    def _on_task_finished(self, url: str, output_path: str) -> None:
        """单个任务完成"""
        self.completed_tasks += 1
        self._log(f"[{url}] ✅ 完成: {output_path}")
        self._schedule_next()

    def _on_task_error(self, url: str, error_msg: str) -> None:
        """单个任务出错"""
        self.failed_tasks += 1
        self.completed_tasks += 1
        self._log(f"[{url}] ❌ 失败: {error_msg}")
        self._schedule_next()

    def _on_all_finished(self) -> None:
        """全部任务完成"""
        self.start_btn.setEnabled(True)
        self.progress_bar.setValue(100)
        success = self.total_tasks - self.failed_tasks
        self.status_label.setText(
            f"状态: 完成 (成功 {success}/{self.total_tasks})")

        self._log("-" * 50)
        self._log(f"全部完成! 成功 {success} 个，失败 {self.failed_tasks} 个")

        # 自动打开输出目录
        if self.auto_open_chk.isChecked() and success > 0:
            try:
                os.startfile(self._output_dir)  # type: ignore[attr-defined]
            except Exception:
                pass

        QMessageBox.information(
            self, "完成",
            f"批量处理完成!\n成功: {success}/{self.total_tasks}\n"
            f"输出目录: {self._output_dir}"
        )

    def _log(self, message: str) -> None:
        """添加日志并自动滚动到底部"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum())

    # ---------- 窗口关闭 ----------

    def closeEvent(self, event) -> None:
        """窗口关闭时确保所有工作线程结束"""
        for worker in self.workers:
            if worker.isRunning():
                worker.wait(3000)
        event.accept()


if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
