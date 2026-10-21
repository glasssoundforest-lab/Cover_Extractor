"""設定ダイアログのバックアップ・復元タブ結合テスト (tests/test_settings_backup_tab.py)
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
from gui_qt.dialogs.settings_dialog import SettingsDialog


class TestSettingsBackupTab(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
        cls.app.setFont(QFont("Yu Gothic UI", 9))
        cls.tmp_dir = tempfile.mkdtemp()
        cls.db_path = os.path.join(cls.tmp_dir, "test_backup.db")
        cls.db = Database(cls.db_path)
        setattr(cls.db, "db_path", cls.db_path)

        cls.original_settings_file = app_settings.SETTINGS_FILE
        cls.test_ini = os.path.join(cls.tmp_dir, "test_settings.ini")
        app_settings.SETTINGS_FILE = cls.test_ini
        app_settings._settings_instance = None

        # テスト用データ登録
        item_id = cls.db.save_item(
            file_path="",
            title="幻影の古城",
            system_name="エモクロアTRPG",
            players_text="2人",
            duration_text="3時間",
            overview="湖畔にそびえる古城を探索するシナリオ。",
            synopsis="あらすじ詳細",
            thumbnail_bytes=None,
        )
        cls.db.add_play_log(item_id, session_date="2026-10-17", role="PL", result="生還")

        cls.artifact_dir = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449"
        os.makedirs(cls.artifact_dir, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        app_settings.SETTINGS_FILE = cls.original_settings_file
        app_settings._settings_instance = None
        shutil.rmtree(cls.tmp_dir, ignore_errors=True)

    def test_backup_tab_ui_and_export_import(self):
        """バックアップ・復元タブのUI表示、統計確認、エクスポートとインポートの動作テスト"""
        dlg = SettingsDialog(self.db)
        dlg.resize(760, 650)
        dlg.show()
        self.app.processEvents()

        # タブ3（インデックス3: バックアップ・復元）に切り替え
        dlg.tabs.setCurrentIndex(3)
        self.app.processEvents()

        # 統計ラベルの確認
        self.assertIn("1", dlg.backup_stats_lbl.text())
        self.assertIn("冊", dlg.backup_stats_lbl.text())

        # スクリーンショット保存
        cap_path = os.path.join(self.artifact_dir, "test_settings_backup_tab.png")
        dlg.grab().save(cap_path)

        # 1. エクスポートのテスト
        export_zip = os.path.join(self.tmp_dir, "test_export_backup.zip")
        with patch("gui_qt.dialogs.settings_dialog.QFileDialog.getSaveFileName", return_value=(export_zip, "")), \
             patch("gui_qt.dialogs.settings_dialog.QMessageBox.information"):
            dlg._on_export_backup()

        self.assertTrue(os.path.exists(export_zip))

        # 2. インポートのテスト
        with patch("gui_qt.dialogs.settings_dialog.QFileDialog.getOpenFileName", return_value=(export_zip, "")), \
             patch("gui_qt.dialogs.settings_dialog.QMessageBox.warning", return_value=16384), \
             patch("gui_qt.dialogs.settings_dialog.QMessageBox.information"):
            dlg._on_import_backup()

        self.app.processEvents()
        # 復元後のDB状態を検証
        stats = self.db.all_records()
        self.assertEqual(len(stats), 1)
        self.assertEqual(stats[0]["title"], "幻影の古城")


if __name__ == "__main__":
    unittest.main()
