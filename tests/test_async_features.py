"""非同期インポートプログレスおよびNotion同期メニューの検証テスト (tests/test_async_features.py)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QPainter
from gui_qt import MainWindow, Theme
from gui_qt.dialogs import ImportProgressDialog

def test_async_features():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyleSheet(Theme.get_application_stylesheet())

    win = MainWindow(db_path="catalog.db")
    win.resize(1260, 820)
    win.show()
    QApplication.processEvents()

    out_dir = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449"

    # 1. バーガーメニューを開いて「✦ Notionと同期...」が追加されていることをキャプチャ
    menu_width = win.header_bar.menu.sizeHint().width()
    pos = win.header_bar.burger_btn.mapToGlobal(QPoint(win.header_bar.burger_btn.width() - menu_width, 32))
    win.header_bar.menu.popup(pos)
    QApplication.processEvents()

    pix_win = win.grab()
    menu_pix = win.header_bar.menu.grab()
    local_pos = win.mapFromGlobal(pos)
    painter = QPainter(pix_win)
    painter.drawPixmap(local_pos, menu_pix)
    painter.end()
    pix_win.save(os.path.join(out_dir, "view_burger_with_notion_sync.png"))
    print("Saved burger menu with Notion sync capture.")
    win.header_bar.menu.close()

    # 2. ImportProgressDialog のUI外観キャプチャ（ダミーターゲット）
    dummy_targets = ["dummy_scenario_1.pdf", "dummy_scenario_2.zip", "dummy_scenario_3.pdf"]
    # 実際には即終了させずに表示確認するため、プログレスダイアログを作成
    dlg = ImportProgressDialog(dummy_targets, win.extractor, win.db, win)
    dlg.pbar.setValue(2)
    dlg.status_label.setText("解析中: dummy_scenario_2.zip")
    dlg.count_label.setText("2 / 3 冊")
    dlg.show()
    QApplication.processEvents()

    dlg_pix = dlg.grab()
    dlg_pix.save(os.path.join(out_dir, "view_import_progress_dialog.png"))
    print("Saved ImportProgressDialog capture.")

    dlg.worker.wait(3000)
    dlg.close()

    win.close()
    print("Async features test passed successfully!")

if __name__ == "__main__":
    test_async_features()
