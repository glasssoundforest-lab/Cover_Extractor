"""下部ステータスバーコンポーネント (gui_qt/components/status_bar.py)

収蔵冊数、選択シナリオ、Rustエンジン状態、操作ヒント、
バックグラウンドで動いている Notion との同調の進み具合を表示します。
"""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QSizeGrip, QProgressBar, QPushButton

from ..theme import Theme


class StatusBar(QWidget):
    """西洋アンティーク調の下部ステータスバー"""
    sync_cancel_requested = Signal()  # 同調の「中断」が押された

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(30)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 4, 8, 4)
        layout.setSpacing(8)

        self.info_label = QLabel("全 0 冊収蔵  │  選択なし  │  Rust Engine: 待機中")
        self.info_label.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 11px;")
        layout.addWidget(self.info_label)

        layout.addStretch()

        # Notion との同調（バックグラウンド）の進み具合。同調していないときは隠しておく
        self.sync_label = QLabel()
        self.sync_label.setStyleSheet(f"color: {Theme.BRASS_LIGHT}; font-size: 11px;")
        self.sync_label.hide()
        layout.addWidget(self.sync_label)

        self.sync_bar = QProgressBar()
        self.sync_bar.setFixedSize(110, 8)
        self.sync_bar.setTextVisible(False)
        self.sync_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: #1a1511;
                border: 1px solid {Theme.BRASS_DARK};
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {Theme.BRASS_BASE};
            }}
        """)
        self.sync_bar.hide()
        layout.addWidget(self.sync_bar)

        self.sync_cancel_btn = QPushButton("中断")
        self.sync_cancel_btn.setFixedSize(44, 20)
        self.sync_cancel_btn.setCursor(Qt.PointingHandCursor)
        self.sync_cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #1e1713;
                color: {Theme.TEXT_MUTED};
                border: 1px solid #4a3a2a;
                border-radius: 2px;
                font-size: 10px;
                font-weight: normal;
                padding: 0px;
            }}
            QPushButton:hover {{
                color: #ffffff;
                border: 1px solid {Theme.BRASS_BASE};
            }}
        """)
        self.sync_cancel_btn.clicked.connect(self._on_sync_cancel)
        self.sync_cancel_btn.hide()
        layout.addWidget(self.sync_cancel_btn)

        self._sync_message_timer = QTimer(self)
        self._sync_message_timer.setSingleShot(True)
        self._sync_message_timer.timeout.connect(self.hide_sync)

        self.hint_label = QLabel("📖  ダブルクリックで本を開く (詳細・あらすじ編集)")
        self.hint_label.setStyleSheet(f"color: {Theme.BRASS_LIGHT}; font-size: 11px;")
        layout.addWidget(self.hint_label)

        # 右下のウィンドウリサイズ用グリップ
        self.size_grip = QSizeGrip(self)
        self.size_grip.setFixedSize(16, 16)
        self.size_grip.setToolTip("ドラッグしてウィンドウサイズを変更")
        self.size_grip.setCursor(Qt.SizeFDiagCursor)
        self.size_grip.setStyleSheet(f"""
            QSizeGrip {{
                background: transparent;
                width: 16px;
                height: 16px;
            }}
        """)
        layout.addWidget(self.size_grip)

    def update_status(self, total_count, selected_title=None, selected_sys=None, rust_ok=True):
        sel_text = f"選択中: {selected_title}" if selected_title else "選択なし"
        if selected_title and selected_sys:
            sel_text += f" ({selected_sys})"

        if rust_ok is None:
            rust_text = "Rust FFI Engine: 準備中…"
        else:
            rust_text = "Rust FFI Engine: 正常稼働中" if rust_ok else "Rust FFI Engine: 未ロード"
        self.info_label.setText(f"全 {total_count} 冊収蔵  │  {sel_text}  │  {rust_text}")

    # -------------------------------------------------------------------------
    # Notion との同調の表示
    # -------------------------------------------------------------------------
    def show_sync_progress(self, current, total, text):
        """同調中の進み具合を表示する（total が 0 のときは進捗の分からない待機表示）"""
        self._sync_message_timer.stop()
        self.hint_label.hide()
        self.sync_label.setText(text)
        self.sync_label.show()
        self.sync_bar.setRange(0, max(0, total))
        if total:
            self.sync_bar.setValue(min(current, total))
        self.sync_bar.show()
        self.sync_cancel_btn.setEnabled(True)
        self.sync_cancel_btn.show()

    def show_sync_message(self, text, timeout_ms=8000):
        """同調の結果などを一定時間表示する"""
        self.hint_label.hide()
        self.sync_bar.hide()
        self.sync_cancel_btn.hide()
        self.sync_label.setText(text)
        self.sync_label.show()
        self._sync_message_timer.start(timeout_ms)

    def hide_sync(self):
        self._sync_message_timer.stop()
        self.sync_label.hide()
        self.sync_bar.hide()
        self.sync_cancel_btn.hide()
        self.hint_label.show()

    def _on_sync_cancel(self):
        self.sync_cancel_btn.setEnabled(False)
        self.sync_label.setText("Notion との同調を中断しています…")
        self.sync_cancel_requested.emit()
