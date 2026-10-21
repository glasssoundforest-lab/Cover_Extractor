"""PySide6 実装アプリケーションの起動・描画検証テスト
"""

import sys
import os

# プロジェクトルートを追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from gui_qt import MainWindow, Theme

def test_run():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyleSheet(Theme.get_application_stylesheet())

    win = MainWindow(db_path="catalog.db")
    win.resize(1260, 800)
    win.show()

    # レンダリングを待機
    QApplication.processEvents()

    # 画面キャプチャを保存
    pix = win.grab()
    out_path = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449\actual_qt_app_running.png"
    pix.save(out_path)
    print("Actual Qt App captured successfully to:", out_path)

    win.close()
    print("Test finished successfully!")

if __name__ == "__main__":
    test_run()
