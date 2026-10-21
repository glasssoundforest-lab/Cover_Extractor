"""Notion設定タブのトークン生成ページ対応およびURLからのID生成機能の検証とスクリーンショット撮影
(tests/test_notion_settings_guide.py)
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
from gui_qt.dialogs.settings_dialog import SettingsDialog, extract_notion_id_from_url

QMessageBox.information = lambda *args, **kwargs: QMessageBox.Ok
QMessageBox.warning = lambda *args, **kwargs: QMessageBox.Ok

ARTIFACT_DIR = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449"

def run_test():
    # 1. 抽出関数の単体テスト
    test_urls = [
        ("https://www.notion.so/my-workspace/TRPG-Archive-8f2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e?v=1234567890abcdef1234567890abcdef", "8f2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e"),
        ("https://www.notion.so/8f2c3d4e-5f6a-7b8c-9d0e-1f2a3b4c5d6e", "8f2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e"),
        ("https://www.notion.so/workspace/8f2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e", "8f2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e"),
    ]
    for url, expected in test_urls:
        extracted = extract_notion_id_from_url(url)
        assert extracted == expected, f"Failed: {url} -> {extracted} != {expected}"
    print("[OK] extract_notion_id_from_url unit tests passed!")

    app = QApplication.instance() or QApplication(sys.argv)

    src_db = os.path.join(ROOT_DIR, "catalog.db")
    test_db_path = os.path.join(ROOT_DIR, "test_notion_guide.db")
    if os.path.exists(src_db):
        shutil.copy2(src_db, test_db_path)

    db = Database(test_db_path)
    dlg = SettingsDialog(db=db)
    dlg.show()
    app.processEvents()

    # タブを「Notion連携・環境」（インデックス4）に切り替え
    dlg.tabs.setCurrentIndex(4)
    app.processEvents()

    def step1_capture_initial():
        """初期画面のキャプチャ"""
        pix = dlg.grab()
        save_path = os.path.join(ARTIFACT_DIR, "settings_notion_tab_initial.png")
        pix.save(save_path)
        print(f"[OK] {save_path} saved")

        QTimer.singleShot(400, step2_paste_url_and_generate_id)

    def step2_paste_url_and_generate_id():
        """URLを入力してIDが自動生成された状態のキャプチャ"""
        test_url = "https://www.notion.so/my-workspace/TRPG-Archive-8f2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e?v=1234567890abcdef1234567890abcdef"
        dlg.page_url_input.setText(test_url)
        app.processEvents()

        # データベースID欄に正しくIDが生成されていることを確認
        assert dlg.db_id_edit.text() == "8f2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e", f"ID mismatch: {dlg.db_id_edit.text()}"

        pix = dlg.grab()
        save_path = os.path.join(ARTIFACT_DIR, "settings_notion_tab_url_generated.png")
        pix.save(save_path)
        print(f"[OK] {save_path} saved")

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
