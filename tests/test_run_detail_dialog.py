"""PySide6 詳細・あらすじ編集ダイアログの起動・描画検証テスト
"""

import sys
import os

# プロジェクトルートを追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication
from core import Database
from gui_qt import Theme
from gui_qt.dialogs import ItemDetailDialog

def test_detail_dialog():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyleSheet(Theme.get_application_stylesheet())

    db = Database("catalog.db")
    items = db.get_items()
    if not items:
        print("No items in catalog.db")
        return

    first_item_id = items[0][0]
    dlg = ItemDetailDialog(first_item_id, db)
    dlg.resize(980, 660)
    dlg.show()

    QApplication.processEvents()

    pix = dlg.grab()
    out_path = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449\actual_qt_detail_running.png"
    pix.save(out_path)
    print("Detail Dialog captured successfully to:", out_path)

    dlg.close()

if __name__ == "__main__":
    test_detail_dialog()
