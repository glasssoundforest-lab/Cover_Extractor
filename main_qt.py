"""PySide6 版 魔導書架 (main_qt.py)

西洋古書・グリモワール調 TRPG シナリオライブラリ管理アプリケーション
"""

import sys
import os

# プロジェクトルートを追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from gui_qt import MainWindow, Theme


def main():
    # 高DPIスケーリングの有効化
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("魔導書架")
    app.setStyleSheet(Theme.get_application_stylesheet())

    window = MainWindow(db_path="catalog.db")
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
