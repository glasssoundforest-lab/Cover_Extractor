"""ショートカット設定ダイアログのGUIテスト (tests/test_shortcut_settings.py)
"""

import sys
import os
import shutil

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QTimer
from PySide6.QtGui import QKeySequence
from gui_qt.dialogs.settings_dialog import SettingsDialog
import app_settings

# テスト中のダイアログブロックを防止
QMessageBox.information = lambda *args, **kwargs: QMessageBox.Ok

ARTIFACT_DIR = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449"

def run_test():
    app = QApplication.instance() or QApplication(sys.argv)

    dlg = SettingsDialog()
    dlg.show()
    app.processEvents()

    # 1. ショートカットタブの表示キャプチャ
    def step1_capture_shortcuts():
        pix = dlg.grab()
        pix.save(os.path.join(ARTIFACT_DIR, "settings_shortcuts_tab.png"))
        print("[OK] settings_shortcuts_tab.png saved")

        # 2. Notionタブへ切り替えてキャプチャ
        dlg.tabs.setCurrentIndex(1)
        QTimer.singleShot(400, step2_capture_notion)

    def step2_capture_notion():
        pix = dlg.grab()
        pix.save(os.path.join(ARTIFACT_DIR, "settings_notion_tab.png"))
        print("[OK] settings_notion_tab.png saved")

        # 3. ショートカットの変更テスト（例: detail_favorite を "G" に変更して保存）
        dlg.tabs.setCurrentIndex(0)
        dlg.shortcut_inputs["detail_favorite"].setKeySequence(QKeySequence("G"))
        dlg._save_settings()

        # 設定が settings.ini に保存されたか確認
        saved = app_settings.get_all_shortcuts()
        assert saved.get("detail_favorite") == "G", f"Expected G, got {saved.get('detail_favorite')}"
        print("[OK] Shortcut detail_favorite changed to G successfully!")

        # 元に戻す
        dlg._reset_shortcuts_to_default()
        dlg._save_settings()
        print("[OK] Reset to default successfully!")

        dlg.close()
        app.quit()

    QTimer.singleShot(500, step1_capture_shortcuts)
    app.exec()

if __name__ == "__main__":
    run_test()
