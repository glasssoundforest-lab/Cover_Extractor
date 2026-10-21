"""バックアップ・復元モジュールの単体テスト (tests/test_backup_manager.py)
"""

import os
import sys
import unittest
import tempfile
import shutil

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.database import Database
from core.backup_manager import BackupManager


class TestBackupManager(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "test.db")
        self.settings_path = os.path.join(self.tmp_dir, "test_settings.ini")
        self.zip_dest = os.path.join(self.tmp_dir, "backup.zip")

        # DB作成とサンプルデータ挿入
        self.db = Database(self.db_path)
        item_id = self.db.save_item(
            file_path="",
            title="星辰の書",
            system_name="CoC",
            players_text="2人",
            duration_text="3時間",
            overview="サンプル概要",
            synopsis="サンプルあらすじ",
            thumbnail_bytes=None,
        )
        self.db.add_play_log(item_id, session_date="2026-10-17", role="GM", result="生還")

        # 設定ファイル作成
        with open(self.settings_path, "w", encoding="utf-8") as f:
            f.write("[domains]\nbooth.pm = Booth\n")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_backup_and_restore(self):
        # 1. バックアップ作成
        info = BackupManager.create_backup(self.zip_dest, self.db_path, self.settings_path)
        self.assertTrue(os.path.exists(self.zip_dest))
        self.assertEqual(info["stats"]["item_count"], 1)
        self.assertEqual(info["stats"]["playlog_count"], 1)

        # 2. バックアップ検査
        inspected = BackupManager.inspect_backup(self.zip_dest)
        self.assertEqual(inspected["stats"]["item_count"], 1)
        self.assertTrue(inspected["contains_db"])
        self.assertTrue(inspected["contains_settings"])

        # 3. 復元先ディレクトリを用意し復元を実行
        restore_dir = os.path.join(self.tmp_dir, "restored")
        os.makedirs(restore_dir, exist_ok=True)
        restored_db = os.path.join(restore_dir, "catalog.db")
        restored_settings = os.path.join(restore_dir, "settings.ini")

        restore_info = BackupManager.restore_backup(
            self.zip_dest,
            db_path=restored_db,
            settings_path=restored_settings,
            restore_settings=True,
        )
        self.assertEqual(restore_info["stats"]["item_count"], 1)
        self.assertTrue(os.path.exists(restored_db))
        self.assertTrue(os.path.exists(restored_settings))

        # 復元されたDBの内容を検証
        db_restored = Database(restored_db)
        items = db_restored.all_records()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "星辰の書")
        logs = db_restored.get_play_logs(items[0]["id"])
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["result"], "生還")


if __name__ == "__main__":
    unittest.main()
