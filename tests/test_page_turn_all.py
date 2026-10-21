"""4冊目（末尾）までのめくりと表紙・お気に入り連動のテスト (tests/test_page_turn_all.py)
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
    test_db_path = os.path.join(ROOT_DIR, "test_turn_all.db")
    if os.path.exists(src_db):
        shutil.copy2(src_db, test_db_path)
    
    db = Database(test_db_path)
    items = db.get_items()
    item_ids = [it[0] for it in items]
    
    # 4冊目をお気に入りに設定してみる
    if len(item_ids) >= 4:
        db.set_favorite(item_ids[3], True)

    dlg = ItemDetailDialog(item_ids[0], db, item_ids=item_ids)
    dlg.show()
    app.processEvents()

    # 一気に4冊目までめくる
    def turn_to_end():
        dlg.next_btn.click() # 2
        dlg.next_btn.click() # 3
        dlg.next_btn.click() # 4
        QTimer.singleShot(400, capture_end)

    def capture_end():
        pix = dlg.grab()
        pix.save(os.path.join(ARTIFACT_DIR, "page_turn_step4_last_book.png"))
        print("[OK] page_turn_step4_last_book.png saved")

        dlg.close()
        try:
            if os.path.exists(test_db_path):
                os.remove(test_db_path)
        except Exception:
            pass
        app.quit()

    QTimer.singleShot(400, turn_to_end)
    app.exec()

if __name__ == "__main__":
    run_test()
