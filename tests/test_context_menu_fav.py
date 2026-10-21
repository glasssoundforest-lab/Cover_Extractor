"""右クリックメニューのお気に入り表示確認テスト (tests/test_context_menu_fav.py)
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

ARTIFACT_DIR = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449"

def run_test():
    app = QApplication.instance() or QApplication(sys.argv)

    src_db = os.path.join(ROOT_DIR, "catalog.db")
    test_db_path = os.path.join(ROOT_DIR, "test_fav_menu.db")
    if os.path.exists(src_db):
        shutil.copy2(src_db, test_db_path)
    
    db = Database(test_db_path)
    items = db.get_items()
    if items:
        db.set_favorite(items[0][0], True)

    window = MainWindow(db_path=test_db_path)
    window.resize(1100, 720)
    window.show()

    def capture_and_close():
        screen = QApplication.primaryScreen()
        pix = screen.grabWindow(0)
        pix.save(os.path.join(ARTIFACT_DIR, "fav_test_context_menu.png"))
        print("[OK] fav_test_context_menu.png saved")
        # 終了
        window.close()
        try:
            if os.path.exists(test_db_path):
                os.remove(test_db_path)
        except Exception:
            pass
        app.quit()

    def open_menu():
        if window.bookshelf.cards:
            card = window.bookshelf.cards[0]
            pt = card.mapToGlobal(QPoint(60, 60))
            # メニューが開いた後に画面を撮影して閉じるタイマーを先に設定
            QTimer.singleShot(400, capture_and_close)
            window._on_card_context_menu(card.item_id, pt)

    QTimer.singleShot(700, open_menu)
    app.exec()

if __name__ == "__main__":
    run_test()
