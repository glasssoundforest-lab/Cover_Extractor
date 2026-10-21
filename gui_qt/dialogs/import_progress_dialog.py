"""非同期シナリオ取り込み・プログレスダイアログ (gui_qt/dialogs/import_progress_dialog.py)

Rust DLL / Python抽出パイプラインを用いた非同期バックグラウンド処理。
大量のPDF/ZIPドラッグ＆ドロップ時にもGUIをフリーズさせず、
真鍮アンティーク調のプログレスバーでリアルタイムに進捗を表示します。
ユーザーによる安全な中断（キャンセル）にも対応します。
"""

import os
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QMessageBox,
)

from ..theme import Theme
from ..components.ornate import OrnateFrame, OrnateDivider, make_fleur_pixmap
from core.extractor import extract_scenario_data


class ImportWorker(QThread):
    """バックグラウンドでシナリオを抽出・データベース保存するワーカー"""
    progress = Signal(int, int, str)      # current_idx, total_count, current_filename
    finished_all = Signal(int, int)       # success_count, fail_count

    def __init__(self, targets, extractor, db, parent=None):
        super().__init__(parent)
        self.targets = targets
        self.extractor = extractor
        self.db_path = getattr(db, "db_path", "catalog.db")

    def run(self):
        from core.database import Database
        worker_db = Database(self.db_path)

        total = len(self.targets)
        success_count = 0
        fail_count = 0

        for idx, target in enumerate(self.targets):
            if self.isInterruptionRequested():
                break

            fname = os.path.basename(target)
            self.progress.emit(idx + 1, total, fname)

            try:
                data = extract_scenario_data(self.extractor, target)
                f = data["fields"]
                item_id = worker_db.save_item(
                    file_path=target,
                    title=data["title"],
                    system_name=f.get("system_name"),
                    players_text=f.get("players_text"),
                    duration_text=f.get("duration_text"),
                    overview=f.get("overview"),
                    synopsis=f.get("synopsis"),
                    thumbnail_bytes=data["thumb_bytes"],
                )
                if data["tags"]:
                    worker_db.add_tags_to_item(item_id, list(data["tags"]))
                success_count += 1
            except Exception as e:
                print(f"[ImportWorker] Error processing {target}: {e}")
                fail_count += 1

        self.finished_all.emit(success_count, fail_count)


class ImportProgressDialog(QDialog):
    """西洋アンティーク調のインポート進捗ダイアログ"""
    def __init__(self, targets, extractor, db, parent=None):
        super().__init__(parent)
        self.targets = targets
        self.extractor = extractor
        self.db = db
        self.success_count = 0
        self.fail_count = 0

        self.setWindowTitle("書架への収蔵処理")
        self.setFixedSize(480, 220)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setStyleSheet(Theme.get_application_stylesheet())

        self._init_ui()
        self._start_worker()

    def _init_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        # 真鍮外枠フレーム
        self.frame = OrnateFrame(self, bracket_size=16, bg_color="#14100c")
        outer_layout.addWidget(self.frame)

        layout = QVBoxLayout(self.frame)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # 見出し
        head_layout = QHBoxLayout()
        fleur = QLabel()
        fleur.setPixmap(make_fleur_pixmap(16, Theme.BRASS_LIGHT))
        head_layout.addWidget(fleur)

        head_title = QLabel("シナリオを解析・収蔵中...")
        head_title.setStyleSheet(f"""
            color: {Theme.BRASS_LIGHT};
            font-size: 14px;
            font-weight: bold;
            font-family: {Theme.FONT_SERIF};
        """)
        head_layout.addWidget(head_title)
        head_layout.addStretch()
        layout.addLayout(head_layout)

        layout.addWidget(OrnateDivider(self, height=8))

        # ファイル名表示ラベル
        self.status_label = QLabel("準備中...")
        self.status_label.setStyleSheet("color: #dcd0bd; font-size: 12px; font-family: serif;")
        layout.addWidget(self.status_label)

        # プログレスバー
        self.pbar = QProgressBar()
        self.pbar.setRange(0, len(self.targets))
        self.pbar.setValue(0)
        self.pbar.setFixedHeight(18)
        self.pbar.setTextVisible(False)
        self.pbar.setStyleSheet(f"""
            QProgressBar {{
                background-color: #1a1511;
                border: 1px solid {Theme.BRASS_BASE};
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #8c703e, stop:1 #d4b26f);
                border-radius: 1px;
            }}
        """)
        layout.addWidget(self.pbar)

        # 件数とキャンセルボタン
        bottom_layout = QHBoxLayout()
        self.count_label = QLabel(f"0 / {len(self.targets)} 冊")
        self.count_label.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 11px;")
        bottom_layout.addWidget(self.count_label)
        bottom_layout.addStretch()

        self.cancel_btn = QPushButton("✕  中断")
        self.cancel_btn.setFixedSize(80, 28)
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #1e1713;
                color: {Theme.TEXT_MUTED};
                border: 1px solid #4a3a2a;
                border-radius: 2px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: #2b211a;
                color: #ffffff;
            }}
        """)
        self.cancel_btn.clicked.connect(self._on_cancel)
        bottom_layout.addWidget(self.cancel_btn)
        layout.addLayout(bottom_layout)

    def _start_worker(self):
        self.worker = ImportWorker(self.targets, self.extractor, self.db, self)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_all.connect(self._on_finished)
        self.worker.start()

    def _on_progress(self, current, total, fname):
        self.pbar.setValue(current)
        self.status_label.setText(f"解析中: {fname}")
        self.count_label.setText(f"{current} / {total} 冊")

    def _on_cancel(self):
        if self.worker.isRunning():
            self.worker.requestInterruption()
            self.status_label.setText("処理を中断しています...")
            self.cancel_btn.setEnabled(False)

    def _on_finished(self, success_count, fail_count):
        self.success_count = success_count
        self.fail_count = fail_count
        if hasattr(self, "worker") and self.worker.isRunning():
            self.worker.wait(1000)
        self.accept()

    def closeEvent(self, event):
        if hasattr(self, "worker") and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait(2000)
        super().closeEvent(event)
