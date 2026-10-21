"""詳細画面の「◀ 前の書物」「次の書物 ▶」めくり機能のテスト (tests/test_page_turn.py)
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
    test_db_path = os.path.join(ROOT_DIR, "test_page_turn.db")
    if os.path.exists(src_db):
        shutil.copy2(src_db, test_db_path)
    
    db = Database(test_db_path)
    items = db.get_items()
    item_ids = [it[0] for it in items]
    first_id = item_ids[0] if item_ids else 1
    
    # 複数IDを渡して詳細ダイアログを開く
    dlg = ItemDetailDialog(first_id, db, item_ids=item_ids)
    dlg.show()
    app.processEvents()

    def step1_capture_first_book():
        # 1冊目のキャプチャ（前へボタンが無効、次へが有効、1/N冊表示）
        pix = dlg.grab()
        pix.save(os.path.join(ARTIFACT_DIR, "page_turn_step1_first_book.png"))
        print("[OK] page_turn_step1_first_book.png saved")

        # 「次の書物 ▶」をクリックして2冊目へめくる
        dlg.next_btn.click()
        QTimer.singleShot(400, step2_capture_second_book)

    def step2_capture_second_book():
        # 2冊目のキャプチャ（前へ・次へ双方が有効、2/N冊表示）
        pix = dlg.grab()
        pix.save(os.path.join(ARTIFACT_DIR, "page_turn_step2_second_book.png"))
        print("[OK] page_turn_step2_second_book.png saved")

        # さらに「次の書物 ▶」をクリックして3冊目へめくる
        dlg.next_btn.click()
        QTimer.singleShot(400, step3_capture_third_book)

    def step3_capture_third_book():
        pix = dlg.grab()
        pix.save(os.path.join(ARTIFACT_DIR, "page_turn_step3_third_book.png"))
        print("[OK] page_turn_step3_third_book.png saved")

        dlg.close()
        try:
            if os.path.exists(test_db_path):
                os.remove(test_db_path)
        except Exception:
            pass
        app.quit()

    QTimer.singleShot(500, step1_capture_first_book)
    app.exec()

if __name__ == "__main__":
    run_test()
