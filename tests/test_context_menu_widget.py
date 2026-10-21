"""右クリックメニュー単体のキャプチャテスト (tests/test_context_menu_widget.py)
"""

import sys
import os
import shutil

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer, QPoint
from core.database import Database
from gui_qt.main_window import MainWindow
from gui_qt.components.tag_context_menu import ScenarioContextMenu

ARTIFACT_DIR = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449"

def run_test():
    app = QApplication.instance() or QApplication(sys.argv)

    src_db = os.path.join(ROOT_DIR, "catalog.db")
    test_db_path = os.path.join(ROOT_DIR, "test_fav_menu.db")
    if os.path.exists(src_db):
        shutil.copy2(src_db, test_db_path)
    
    db = Database(test_db_path)
    items = db.get_items()
    first_id = items[0][0] if items else 1
    
    # 1. お気に入り ON の状態のメニュー
    db.set_favorite(first_id, True)
    menu_fav = ScenarioContextMenu(first_id, db)
    menu_fav.show()
    app.processEvents()
    pix1 = menu_fav.grab()
    pix1.save(os.path.join(ARTIFACT_DIR, "context_menu_fav_on.png"))
    print("[OK] context_menu_fav_on.png saved")
    menu_fav.close()

    # 2. お気に入り OFF の状態のメニュー
    db.set_favorite(first_id, False)
    menu_unfav = ScenarioContextMenu(first_id, db)
    menu_unfav.show()
    app.processEvents()
    pix2 = menu_unfav.grab()
    pix2.save(os.path.join(ARTIFACT_DIR, "context_menu_fav_off.png"))
    print("[OK] context_menu_fav_off.png saved")
    menu_unfav.close()

    try:
        if os.path.exists(test_db_path):
            os.remove(test_db_path)
    except Exception:
        pass
    app.quit()

if __name__ == "__main__":
    run_test()
