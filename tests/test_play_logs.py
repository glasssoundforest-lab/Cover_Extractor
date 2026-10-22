"""セッション履歴（セッション履歴・プレイログ）機能の結合テスト (tests/test_play_logs.py)
"""

import os
import sys
import unittest
import tempfile
import shutil
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

import app_settings
from core.database import Database
from gui_qt.dialogs.item_detail_dialog import ItemDetailDialog
from gui_qt.dialogs.play_log_dialog import PlayLogEditDialog


class TestPlayLogs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
        cls.app.setFont(QFont("Yu Gothic UI", 9))
        cls.tmp_dir = tempfile.mkdtemp()
        cls.db_path = os.path.join(cls.tmp_dir, "test_play_logs.db")
        cls.db = Database(cls.db_path)

        cls.original_settings_file = app_settings.SETTINGS_FILE
        cls.test_ini = os.path.join(cls.tmp_dir, "test_settings.ini")
        app_settings.SETTINGS_FILE = cls.test_ini
        app_settings._settings_instance = None

        # テスト用アイテム
        cls.item_id = cls.db.save_item(
            file_path="",
            title="ネームレス・カルト",
            system_name="クトゥルフ神話TRPG",
            players_text="3人",
            duration_text="4時間",
            overview="怪異と対峙する探索者たちの記録。",
            synopsis="古き呪われた館を舞台にした探索シナリオ。",
            thumbnail_bytes=None,
        )

        cls.artifact_dir = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449"
        os.makedirs(cls.artifact_dir, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        app_settings.SETTINGS_FILE = cls.original_settings_file
        app_settings._settings_instance = None
        shutil.rmtree(cls.tmp_dir, ignore_errors=True)

    def test_01_database_play_logs_crud(self):
        """Databaseクラスのplay_logsテーブルCRUD操作のテスト"""
        # 1. 追加
        log_id = self.db.add_play_log(
            item_id=self.item_id,
            session_date="2026-10-15",
            role="KP / GM (ゲームマスター)",
            party_members="Aさん, Bさん, Cさん",
            character_name="",
            result="全員生還",
            memo="素晴らしいRPで全員生還を果たした。",
        )
        self.assertIsInstance(log_id, int)

        # 2. 取得
        logs = self.db.get_play_logs(self.item_id)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["session_date"], "2026-10-15")
        self.assertEqual(logs[0]["result"], "全員生還")

        # 3. 更新
        self.db.update_play_log(
            log_id=log_id,
            session_date="2026-10-16",
            role="KP / GM (ゲームマスター)",
            party_members="Aさん, Bさん, Cさん, Dさん",
            character_name="",
            result="全員生還 (END-A)",
            memo="4人卓で大盛り上がり。",
        )
        logs = self.db.get_play_logs(self.item_id)
        self.assertEqual(logs[0]["session_date"], "2026-10-16")
        self.assertIn("END-A", logs[0]["result"])

        # 4. 削除
        self.db.delete_play_log(log_id)
        logs = self.db.get_play_logs(self.item_id)
        self.assertEqual(len(logs), 0)

    def test_02_dialog_integration_and_auto_passed_tag(self):
        """詳細画面でのセッション履歴追加と『通過済』タグ自動付与のテスト"""
        dlg = ItemDetailDialog(self.item_id, self.db, None, item_ids=[self.item_id])
        dlg.resize(1020, 890)
        dlg.show()
        self.app.processEvents()

        # 初期状態: 記録なし
        self.assertEqual(len(self.db.get_play_logs(self.item_id)), 0)

        # 記録を追加（PlayLogEditDialogの実行をモック）
        fake_log = {
            "session_date": "2026-10-17",
            "role": "PL (プレイヤー)",
            "character_name": "羽鳥 潤 (探偵)",
            "result": "生還",
            "party_members": "GM: 佐藤さん, PL: 田中さん, 鈴木さん",
            "memo": "クライマックスのSANチェックを1クリで乗り切って生還！熱いセッションだった。",
        }

        with patch("gui_qt.dialogs.play_log_dialog.PlayLogEditDialog") as mock_dlg_cls, \
             patch("gui_qt.dialogs.item_detail_dialog.QMessageBox.information"):
            mock_inst = MagicMock()
            mock_inst.exec.return_value = 1
            mock_inst.result_data = fake_log
            mock_dlg_cls.return_value = mock_inst
            dlg._on_add_play_log()

        self.app.processEvents()

        # DBに記録が保存されたこと
        logs = self.db.get_play_logs(self.item_id)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["character_name"], "羽鳥 潤 (探偵)")

        # 「通過済み」タグが自動付与されていること
        item_tags = [t[1] for t in self.db.get_item_tags(self.item_id)]
        self.assertIn("通過済み", item_tags)

        # キャプチャ保存
        cap_path = os.path.join(self.artifact_dir, "test_detail_play_logs_view.png")
        dlg.grab().save(cap_path)


if __name__ == "__main__":
    unittest.main()
