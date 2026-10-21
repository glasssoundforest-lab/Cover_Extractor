"""下部ステータスバーコンポーネント (gui_qt/components/status_bar.py)

収蔵冊数、選択シナリオ、Rustエンジン状態、操作ヒントを表示します。
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QSizeGrip

from ..theme import Theme


class StatusBar(QWidget):
    """西洋アンティーク調の下部ステータスバー"""
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
