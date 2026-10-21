"""お気に入り機能のGUI検証テスト (tests/test_favorite_feature.py)

1. 表紙左上の星バッジ表示確認
2. サイドバー「★ お気に入り」項目と件数表示確認
3. お気に入り絞り込み表示確認
4. 2カラム一覧表示での星バッジ確認
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
from gui_qt.main_window import MainWindow

ARTIFACT_DIR = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449"

def run_test():
    app = QApplication.instance() or QApplication(sys.argv)

    src_db = os.path.join(ROOT_DIR, "catalog.db")
    test_db_path = os.path.join(ROOT_DIR, "test_fav.db")
    if os.path.exists(src_db):
        shutil.copy2(src_db, test_db_path)
    
    db = Database(test_db_path)
    items = db.get_items()
    if items:
        # 最初のアイテムをお気に入りに設定、2番目以降は非お気に入り
        db.set_favorite(items[0][0], True)
        for it in items[1:]:
            db.set_favorite(it[0], False)

    window = MainWindow(db_path=test_db_path)
    window.resize(1100, 720)
    window.show()

    def step1_capture_main():
        # 1. メイン画面（1冊目のお気に入り星バッジ、サイドバーの★お気に入り（1）を確認）
        pix = window.grab()
        pix.save(os.path.join(ARTIFACT_DIR, "fav_test_main_view.png"))
        print("[OK] fav_test_main_view.png saved")

        # 2. 「★ お気に入り」をクリックして絞り込み
        window.sidebar._on_category_clicked("__favorite__")
        QTimer.singleShot(500, step2_capture_favorite_filter)

    def step2_capture_favorite_filter():
        # お気に入りのみ（1冊）が表示されることを確認
        pix = window.grab()
        pix.save(os.path.join(ARTIFACT_DIR, "fav_test_filtered_view.png"))
        print("[OK] fav_test_filtered_view.png saved")

        # 3. 2カラム一覧表示モードでも星バッジを確認
        window.header_bar.view_mode_changed.emit("list")
        QTimer.singleShot(500, step3_capture_list_view)

    def step3_capture_list_view():
        pix = window.grab()
        pix.save(os.path.join(ARTIFACT_DIR, "fav_test_list_view.png"))
        print("[OK] fav_test_list_view.png saved")

        # クリーンアップして終了
        window.close()
        try:
            if os.path.exists(test_db_path):
                os.remove(test_db_path)
        except Exception:
            pass
        app.quit()

    QTimer.singleShot(800, step1_capture_main)
    app.exec()

if __name__ == "__main__":
    run_test()
