"""詳細ダイアログのお気に入り表示テスト (tests/test_detail_fav.py)
"""

import sys
import os
import shutil

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from core.database import Database
from gui_qt.dialogs.item_detail_dialog import ItemDetailDialog

ARTIFACT_DIR = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449"

def run_test():
    app = QApplication.instance() or QApplication(sys.argv)

    src_db = os.path.join(ROOT_DIR, "catalog.db")
    test_db_path = os.path.join(ROOT_DIR, "test_detail_fav.db")
    if os.path.exists(src_db):
        shutil.copy2(src_db, test_db_path)
    
    db = Database(test_db_path)
    items = db.get_items()
    first_id = items[0][0] if items else 1
    
    # お気に入り ON で開く
    db.set_favorite(first_id, True)
    dlg = ItemDetailDialog(first_id, db)
    dlg.show()
    app.processEvents()

    pix = dlg.grab()
    pix.save(os.path.join(ARTIFACT_DIR, "detail_dialog_with_favorite.png"))
    print("[OK] detail_dialog_with_favorite.png saved")

    dlg.close()
    try:
        if os.path.exists(test_db_path):
            os.remove(test_db_path)
    except Exception:
        pass
    app.quit()

if __name__ == "__main__":
    run_test()
