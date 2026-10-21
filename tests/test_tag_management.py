"""タグ一覧管理画面のテスト (tests/test_tag_management.py)
"""

import sys
import os
import shutil

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QTimer
from core.database import Database
from gui_qt.dialogs.settings_dialog import SettingsDialog

QMessageBox.information = lambda *args, **kwargs: QMessageBox.Ok
QMessageBox.question = lambda *args, **kwargs: QMessageBox.Yes

ARTIFACT_DIR = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449"

def run_test():
    app = QApplication.instance() or QApplication(sys.argv)

    src_db = os.path.join(ROOT_DIR, "catalog.db")
    test_db_path = os.path.join(ROOT_DIR, "test_tag_mgmt.db")
    if os.path.exists(src_db):
        shutil.copy2(src_db, test_db_path)

    db = Database(test_db_path)
    dlg = SettingsDialog(db=db)
    dlg.show()
    app.processEvents()

    # 1. 初期状態のタグ管理画面キャプチャ
    def step1_capture_initial():
        pix = dlg.grab()
        pix.save(os.path.join(ARTIFACT_DIR, "settings_tags_tab_initial.png"))
        print("[OK] settings_tags_tab_initial.png saved")

        # 2. 新規タグを追加
        dlg.new_tag_input.setText("ソロシナリオ")
        dlg._on_add_tag()
        QTimer.singleShot(400, step2_capture_added)

    def step2_capture_added():
        pix = dlg.grab()
        pix.save(os.path.join(ARTIFACT_DIR, "settings_tags_tab_added.png"))
        print("[OK] settings_tags_tab_added.png saved")

        # 3. 絞り込みテスト
        dlg.tag_filter_input.setText("CoC")
        QTimer.singleShot(400, step3_capture_filtered)

    def step3_capture_filtered():
        pix = dlg.grab()
        pix.save(os.path.join(ARTIFACT_DIR, "settings_tags_tab_filtered.png"))
        print("[OK] settings_tags_tab_filtered.png saved")

        dlg.close()
        try:
            if os.path.exists(test_db_path):
                os.remove(test_db_path)
        except Exception:
            pass
        app.quit()

    QTimer.singleShot(500, step1_capture_initial)
    app.exec()

if __name__ == "__main__":
    run_test()
