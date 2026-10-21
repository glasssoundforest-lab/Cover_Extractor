"""URL追加機能および情報元FlowLayout折り返し表示の統合テストスクリプト"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch
from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import QApplication

# プロジェクトルートを追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import Database
from gui_qt.dialogs.item_detail_dialog import ItemDetailDialog
from gui_qt.dialogs.add_scenario_url_dialog import AddScenarioUrlDialog
from gui_qt.main_window import MainWindow


class TestUrlImportAndSourceFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
        cls.db_path = ":memory:"
        cls.artifact_dir = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449"
        os.makedirs(cls.artifact_dir, exist_ok=True)

    def setUp(self):
        self.db = Database(self.db_path)
        # テスト用アイテムの作成（ファイル、WEB、Notionが全て揃った状態）
        self.item_id_full = self.db.save_item(
            file_path=r"C:\Scenarios\test_scenario_book.pdf",
            title="星辰の記憶と黄昏の古城",
            system_name="クトゥルフ神話TRPG",
            players_text="3-4人",
            duration_text="3時間",
            overview="探索者たちは人里離れた古城で不可思議な手記を発見する。",
            synopsis="星々が正しい位置に戻る時、古き扉が開かれる。探索者たちは失われた記憶を取り戻すため古城を探索する。",
            thumbnail_bytes=None,
        )
        self.db.update_item_meta(
            self.item_id_full,
            title="星辰の記憶と黄昏の古城",
            system_name="クトゥルフ神話TRPG",
            players_text="3-4人",
            duration_text="3時間",
            author="深淵探求録",
        )
        self.db.set_source_url(
            self.item_id_full,
            "https://booth.pm/ja/items/7891055?very_long_parameter_for_flow_layout_wrapping=true",
        )
        self.db.set_notion_link(
            self.item_id_full,
            "12345678-1234-1234-1234-123456789abc",
            notion_url="https://www.notion.so/test-workspace/Star-Memory-12345678123412341234123456789abc",
        )

    def tearDown(self):
        try:
            self.db.conn.close()
        except Exception:
            pass

    def test_01_source_flow_order_and_wrapping(self):
        """詳細画面の情報元がファイル、WEBサイト、Notionの順序で並び、FlowLayoutにより折り返されること"""
        dlg = ItemDetailDialog(self.item_id_full, self.db, None, item_ids=[self.item_id_full])
        dlg.resize(980, 720)
        dlg.show()
        self.app.processEvents()

        # 順序の検証: source_view_layout の要素順序
        # 0: file_item_widget
        # 1: web_item_widget
        # 2: notion_item_widget
        self.assertEqual(dlg.source_view_layout.itemAt(0).widget(), dlg.file_item_widget)
        self.assertEqual(dlg.source_view_layout.itemAt(1).widget(), dlg.web_item_widget)
        self.assertEqual(dlg.source_view_layout.itemAt(2).widget(), dlg.notion_item_widget)

        # ファイル・WEB・Notionがすべて表示されていること
        self.assertFalse(dlg.file_item_widget.isHidden())
        self.assertFalse(dlg.web_item_widget.isHidden())
        self.assertFalse(dlg.notion_item_widget.isHidden())

        # スクリーンショット（通常幅）
        pix_full = dlg.grab()
        cap_path_full = os.path.join(self.artifact_dir, "test_detail_source_flow_layout.png")
        pix_full.save(cap_path_full)
        self.assertTrue(os.path.exists(cap_path_full))

        # ダイアログの横幅を狭めて折り返しを強制
        dlg.resize(800, 720)
        self.app.processEvents()
        pix_narrow = dlg.grab()
        cap_path_narrow = os.path.join(self.artifact_dir, "test_detail_source_flow_wrapped.png")
        pix_narrow.save(cap_path_narrow)
        self.assertTrue(os.path.exists(cap_path_narrow))

        dlg.close()
        self.app.processEvents()

    def test_02_add_scenario_url_dialog_ui(self):
        """URLからシナリオ追加ダイアログが正常に起動し、UI要素が表示されること"""
        url_dlg = AddScenarioUrlDialog(self.db, initial_url="https://booth.pm/ja/items/7891055")
        url_dlg.show()
        self.app.processEvents()

        self.assertIn("https://booth.pm/ja/items/7891055", url_dlg.url_input.text())
        self.assertIn("Web サイト", url_dlg.preview_lbl.text())

        pix = url_dlg.grab()
        cap_path = os.path.join(self.artifact_dir, "test_add_scenario_url_dialog.png")
        pix.save(cap_path)
        self.assertTrue(os.path.exists(cap_path))

        # Notion URL に切り替えた時の自動判定テスト
        url_dlg.url_input.setText("https://www.notion.so/my-org/Scenario-Page-abcdef1234567890abcdef1234567890")
        self.app.processEvents()
        self.assertIn("Notion ページ", url_dlg.preview_lbl.text())

        pix_notion = url_dlg.grab()
        cap_path_notion = os.path.join(self.artifact_dir, "test_add_scenario_url_dialog_notion.png")
        pix_notion.save(cap_path_notion)
        self.assertTrue(os.path.exists(cap_path_notion))

        url_dlg.close()
        self.app.processEvents()

    def test_03_main_window_add_menu(self):
        """メインウィンドウの『＋ シナリオを追加』メニューおよびURL取り込み接続のテスト"""
        win = MainWindow(db_path=self.db_path)
        win.resize(1200, 800)
        win.show()
        self.app.processEvents()

        # ヘッダーバーの追加ボタンのクリックによりメニューが立ち上がること
        btn = win.header_bar.add_btn
        self.assertTrue(btn.isVisible())

        # シグナル発火テスト
        with patch.object(win, "_on_import_url_requested") as mock_url_req:
            win.header_bar.import_url_requested.emit()
            mock_url_req.assert_called_once()

        win.close()
        self.app.processEvents()

    def test_04_import_existing_scenario_from_web(self):
        """既に登録されているシナリオをWEB経由で取り込もうとした時、取得失敗とならず正常に更新・照合されること"""
        # 1. 既に登録されているURL（self.item_id_full）でWebデータを更新
        updated_data = {
            "title": "星辰の記憶と黄昏の古城（改訂版）",
            "author": "深淵探求録（新）",
            "system": "新クトゥルフ神話TRPG",
            "players": "4人",
            "duration": "4時間",
            "overview": "改訂版の概要テキストです。",
            "synopsis": "改訂版のあらすじテキストです。",
            "image_bytes": b"fake_png_data",
        }
        target_url = "https://booth.pm/ja/items/7891055?very_long_parameter_for_flow_layout_wrapping=true"

        # WebScenarioExtractor をモックしてダイアログ経由で取り込み実行
        with patch("core.web_extractor.WebScenarioExtractor.extract_from_url", return_value=updated_data), \
             patch("gui_qt.dialogs.web_info_diff_dialog.WebInfoComparisonDialog.exec", return_value=1), \
             patch("gui_qt.dialogs.web_info_diff_dialog.WebInfoComparisonDialog.get_selected_fields", return_value={"title", "author", "system", "players", "duration", "overview", "synopsis", "cover", "tags"}):
            dlg = AddScenarioUrlDialog(self.db, initial_url=target_url)
            item_id, title = dlg._import_from_web(target_url)

            # 既存のアイテムIDが返ってくること
            self.assertEqual(item_id, self.item_id_full)
            self.assertEqual(title, "星辰の記憶と黄昏の古城（改訂版）")

            # DBが正しく更新されていること
            item = self.db.get_item(self.item_id_full)
            # 既存のローカルファイルパスが温存されていること
            self.assertEqual(item[1], r"C:\Scenarios\test_scenario_book.pdf")
            self.assertEqual(item[2], "星辰の記憶と黄昏の古城（改訂版）")
            self.assertEqual(item[3], "新クトゥルフ神話TRPG")
            self.assertEqual(item[4], "4人")
            self.assertEqual(item[5], "4時間")
            self.assertEqual(item[6], "改訂版の概要テキストです。")
            self.assertEqual(item[7], "改訂版のあらすじテキストです。")
            self.assertEqual(item[8], b"fake_png_data")

            # CoCおよび4人PLのタグが付与されていること
            tags = [t[1] for t in self.db.get_item_tags(self.item_id_full)]
            self.assertIn("CoC", tags)
            self.assertIn("4PL", tags)

        # 2. ローカルファイルのみで登録されているシナリオと同じタイトルでWeb取り込みした場合の照合テスト
        local_item_id = self.db.save_item(
            file_path=r"C:\Scenarios\local_only_scenario.pdf",
            title="雪山密室殺人事件",
            system_name="エモクロアTRPG",
            players_text="2人",
            duration_text="2時間",
            overview="雪山の山荘で起きた密室殺人。",
            synopsis="猛吹雪の中、電話線が切断された山荘――。",
            thumbnail_bytes=None,
        )

        web_data_match_title = {
            "title": "雪山密室殺人事件",
            "author": "推理工房",
            "system": "エモクロアTRPG",
            "players": "2人",
            "duration": "2.5時間",
            "overview": "雪山の山荘で起きた完全密室殺人事件。",
            "synopsis": "猛吹雪の中、閉ざされた山荘で起きる惨劇。",
            "image_bytes": b"web_cover",
        }
        new_web_url = "https://booth.pm/ja/items/9999999"

        with patch("core.web_extractor.WebScenarioExtractor.extract_from_url", return_value=web_data_match_title), \
             patch("gui_qt.dialogs.web_info_diff_dialog.WebInfoComparisonDialog.exec", return_value=1), \
             patch("gui_qt.dialogs.web_info_diff_dialog.WebInfoComparisonDialog.get_selected_fields", return_value={"title", "author", "system", "players", "duration", "overview", "synopsis", "cover", "tags"}):
            dlg2 = AddScenarioUrlDialog(self.db, initial_url=new_web_url)
            ret_id, ret_title = dlg2._import_from_web(new_web_url)

            # 既存の local_item_id と照合されてマージされること
            self.assertEqual(ret_id, local_item_id)
            item_local = self.db.get_item(local_item_id)
            # ローカルファイルパスが消えず残っていること
            self.assertEqual(item_local[1], r"C:\Scenarios\local_only_scenario.pdf")
            # Web URLが情報元として紐付いていること
            self.assertEqual(self.db.get_source_url(local_item_id), new_web_url)
            # 作者が登録されていること
            self.assertEqual(self.db.get_author(local_item_id), "推理工房")

    def test_05_comparison_dialog_shown_on_import(self):
        """取り込み時にWebInfoComparisonDialogが実際に表示され、比較UIが機能すること"""
        from gui_qt.dialogs.web_info_diff_dialog import WebInfoComparisonDialog

        current_data = {
            "title": "星辰の記憶と黄昏の古城",
            "author": "深淵探求録",
            "system": "クトゥルフ神話TRPG",
            "players": "3-4人",
            "duration": "3時間",
            "overview": "探索者たちは人里離れた古城で不可思議な手記を発見する。",
            "synopsis": "星々が正しい位置に戻る時、古き扉が開かれる。",
            "thumbnail_bytes": None,
        }
        web_data = {
            "title": "星辰の記憶と黄昏の古城（改訂版）",
            "author": "深淵探求録（最新）",
            "system": "新クトゥルフ神話TRPG",
            "players": "4人推奨",
            "duration": "3〜4時間",
            "overview": "最新版の概要テキストです。",
            "synopsis": "最新版のあらすじテキストです。",
            "image_bytes": None,
        }

        diff_dlg = WebInfoComparisonDialog(
            current_data=current_data,
            web_data=web_data,
            source_name="Web情報",
        )
        diff_dlg.resize(800, 700)
        diff_dlg.show()
        self.app.processEvents()

        # 変更点が検出されチェックボックスが有効であること
        selected = diff_dlg.get_selected_fields()
        self.assertIn("title", selected)
        self.assertIn("overview", selected)

        # 比較画面のスクリーンショット保存
        pix = diff_dlg.grab()
        cap_path = os.path.join(self.artifact_dir, "test_add_scenario_comparison_dialog.png")
        pix.save(cap_path)
        self.assertTrue(os.path.exists(cap_path))

        diff_dlg.close()
        self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
