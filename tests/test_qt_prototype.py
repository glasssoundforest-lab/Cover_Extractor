"""PySide6 プロトタイプウィンドウ検証スクリプト (tests/test_qt_prototype.py)

データ層 (Database) および Rust DLL (RustDllExtractor) と連携し、
PySide6 の画面上で正常にサムネイルとメタデータが描画できるかを検証します。
結果を画像 (preview_qt_prototype.png) として保存します。
"""

import sys
import os

# プロジェクトルートを追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import Qt, QByteArray, QSize
from PySide6.QtGui import QPixmap, QIcon, QFont, QColor
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QFrame,
    QGridLayout,
)

from core import Database, RustDllExtractor
from gui_qt.theme import Theme


class ScenarioCard(QFrame):
    """西洋古書・羊皮紙風のシナリオカードウィジェット"""
    def __init__(self, item, parent=None):
        super().__init__(parent)
        self.item = item
        self.setFixedSize(180, 260)
        self.setCursor(Qt.PointingHandCursor)

        # 羊皮紙カードスタイル
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.BG_CARD};
                border: 2px solid {Theme.BRASS_BASE};
                border-radius: 6px;
            }}
            QFrame:hover {{
                background-color: {Theme.BG_CARD_HOVER};
                border: 2px solid {Theme.BRASS_LIGHT};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 表紙サムネイル
        self.thumb_label = QLabel(self)
        self.thumb_label.setFixedSize(164, 180)
        self.thumb_label.setAlignment(Qt.AlignCenter)
        self.thumb_label.setStyleSheet(f"""
            background-color: #1a1614;
            border: 1px solid {Theme.BRASS_DARK};
            border-radius: 3px;
        """)

        thumb_bytes = item[8]
        if thumb_bytes:
            pix = QPixmap()
            pix.loadFromData(QByteArray(thumb_bytes))
            if not pix.isNull():
                scaled_pix = pix.scaled(
                    164, 180, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                self.thumb_label.setPixmap(scaled_pix)
            else:
                self.thumb_label.setText("No Image")
                self.thumb_label.setStyleSheet("color: #8c733e;")
        else:
            self.thumb_label.setText("No Image")
            self.thumb_label.setStyleSheet("color: #8c733e;")

        layout.addWidget(self.thumb_label)

        # タイトル
        title_text = item[2] or "無題"
        self.title_label = QLabel(title_text, self)
        self.title_label.setWordWrap(True)
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet(f"""
            color: {Theme.TEXT_WHITE};
            font-weight: bold;
            font-size: 12px;
            background: transparent;
            border: none;
        """)
        layout.addWidget(self.title_label)

        # システム名
        sys_text = item[3] or "システム未設定"
        self.sys_label = QLabel(sys_text, self)
        self.sys_label.setAlignment(Qt.AlignCenter)
        self.sys_label.setStyleSheet(f"""
            color: {Theme.TEXT_MUTED};
            font-size: 11px;
            background: transparent;
            border: none;
        """)
        layout.addWidget(self.sys_label)


class PrototypeWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TRPG Cover Extractor - PySide6 Prototype")
        self.resize(800, 500)

        # データ層とRust連携の初期化
        self.db = Database("catalog.db")
        try:
            self.extractor = RustDllExtractor()
            dll_status = "Rust DLL: 正常稼働中"
        except Exception as e:
            self.extractor = None
            dll_status = f"Rust DLL: ロード失敗 ({e})"

        # 全体ウィジェット
        central = QWidget(self)
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # ヘッダーバー
        header = QHBoxLayout()
        title = QLabel("書架 - TRPG Scenario Library")
        title.setStyleSheet(f"""
            font-size: 18px;
            font-weight: bold;
            color: {Theme.BRASS_LIGHT};
            font-family: {Theme.FONT_SERIF};
        """)
        header.addWidget(title)

        status_lbl = QLabel(dll_status)
        status_lbl.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 11px;")
        header.addStretch()
        header.addWidget(status_lbl)
        main_layout.addLayout(header)

        # スクロールエリア（本棚グリッド）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")

        shelf_widget = QWidget()
        shelf_widget.setStyleSheet(f"background-color: {Theme.BG_SHELF}; border-radius: 6px;")
        grid = QGridLayout(shelf_widget)
        grid.setSpacing(16)
        grid.setContentsMargins(16, 16, 16, 16)

        # データベースからシナリオ取得
        items = self.db.get_items()
        cols = 3
        for idx, item in enumerate(items):
            card = ScenarioCard(item)
            grid.addWidget(card, idx // cols, idx % cols)

        grid.setRowStretch(len(items) // cols + 1, 1)
        grid.setColumnStretch(cols, 1)

        scroll.setWidget(shelf_widget)
        main_layout.addWidget(scroll)


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyleSheet(Theme.get_application_stylesheet())

    win = PrototypeWindow()
    win.show()

    # レンダリング完了を待って画面キャプチャを保存
    QApplication.processEvents()
    pix = win.grab()
    out_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "preview_qt_prototype.png",
    )
    pix.save(out_path)
    print(f"Prototype rendered and captured successfully to: {out_path}")


if __name__ == "__main__":
    main()
