"""Notionからのデータ読み込み・切り分け（シナリオ名・表紙・タグ等）およびDB登録の総合テスト
(tests/test_notion_import_db.py)

検証項目:
1. Notion ページの JSON からシナリオ名(title)、表紙URL(cover / filesプロパティ)、タグ(multi_select / rich_text)が正しく切り分けられること
2. import_from_notion によってシナリオ名、表紙バイナリ(thumbnail)、タグ(グローバルタグ・ローカルタグの自動判別と正規化)がDBへ正しく登録されること
3. 同一 page_id の再読み込み時に重複登録されず、既存レコードが適切に更新されること
4. NotionSyncWorker の実行によって Notion から読み込まれたデータが DB に保存され、詳細画面(ItemDetailDialog)にも正しく反映されること
"""

import io
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PIL import Image
from PySide6.QtWidgets import QApplication

import app_settings
import notion_sync
from core.database import Database
from gui_qt.dialogs.item_detail_dialog import ItemDetailDialog
from gui_qt.dialogs.notion_sync_dialog import NotionSyncWorker


def _make_dummy_image_bytes(color=(120, 40, 40), size=(120, 170)) -> bytes:
    """テスト用のダミー表紙画像（JPEGバイト列）を生成する"""
    buf = io.BytesIO()
    img = Image.new("RGB", size, color=color)
    img.save(buf, format="JPEG")
    return buf.getvalue()


class TestNotionImportToDB(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
        cls.tmp_dir = tempfile.mkdtemp()
        cls.db_path = os.path.join(cls.tmp_dir, "test_notion_import.db")
        cls.db = Database(cls.db_path)

        cls.original_settings_file = app_settings.SETTINGS_FILE
        cls.test_ini = os.path.join(cls.tmp_dir, "test_settings.ini")
        app_settings.SETTINGS_FILE = cls.test_ini
        app_settings._settings_instance = None

        # ダミー表紙バイナリを2種類用意
        cls.cover_bytes_1 = _make_dummy_image_bytes(color=(30, 80, 140))
        cls.cover_bytes_2 = _make_dummy_image_bytes(color=(140, 50, 30))

        # 模擬 Notion スキーマ
        cls.mock_schema = {
            "シナリオ名": "title",
            "よみ": "rich_text",
            "作者": "rich_text",
            "システム": "select",
            "PL人数": "number",
            "所要時間": "number",
            "概要": "rich_text",
            "あらすじ": "rich_text",
            "タグ": "multi_select",
            "販売URL": "url",
            "表紙": "files",
        }

        # 模擬 Notion ページデータ (2件)
        # 1件目: ページカバー(cover)あり + multi_selectタグ（グローバルタグ＋ローカルタグ混在）
        cls.mock_page_1 = {
            "object": "page",
            "id": "11111111-2222-3333-4444-555555555555",
            "archived": False,
            "in_trash": False,
            "cover": {
                "type": "external",
                "external": {"url": "https://images.example.com/covers/kyoki_sanmyaku.jpg"},
            },
            "properties": {
                "シナリオ名": {
                    "type": "title",
                    "title": [
                        {"plain_text": "狂気山脈 "},
                        {"plain_text": "〜邪神の山嶺〜"},
                    ],
                },
                "よみ": {
                    "type": "rich_text",
                    "rich_text": [{"plain_text": "きょうきさんみゃく"}],
                },
                "作者": {
                    "type": "rich_text",
                    "rich_text": [{"plain_text": "まだら牛"}],
                },
                "システム": {
                    "type": "select",
                    "select": {"name": "クトゥルフ神話TRPG"},
                },
                "PL人数": {
                    "type": "number",
                    "number": 4,
                },
                "所要時間": {
                    "type": "number",
                    "number": 6,
                },
                "概要": {
                    "type": "rich_text",
                    "rich_text": [{"plain_text": "南極最高峰に挑む登山家たちの過酷な挑戦。"}],
                },
                "あらすじ": {
                    "type": "rich_text",
                    "rich_text": [{"plain_text": "1930年代、南極大陸。前人未到の山脈へ挑む。"}],
                },
                "タグ": {
                    "type": "multi_select",
                    "multi_select": [
                        {"name": "CoC"},
                        {"name": "未通過"},
                        {"name": "山岳ホラー"},
                        {"name": "秘匿HO"},
                    ],
                },
                "販売URL": {
                    "type": "url",
                    "url": "https://dappleox.booth.pm/items/1234567",
                },
                "表紙": {
                    "type": "files",
                    "files": [],
                },
            },
        }

        # 2件目: ページcoverはNoneだが「表紙」filesプロパティに画像あり + 表記揺れタグ（「クトゥルフ」「通過済み」）
        cls.mock_page_2 = {
            "object": "page",
            "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "archived": False,
            "in_trash": False,
            "cover": None,
            "properties": {
                "シナリオ名": {
                    "type": "title",
                    "title": [{"plain_text": "カタシロ"}],
                },
                "よみ": {
                    "type": "rich_text",
                    "rich_text": [{"plain_text": "かたしろ"}],
                },
                "作者": {
                    "type": "rich_text",
                    "rich_text": [{"plain_text": "ディズム"}],
                },
                "システム": {
                    "type": "select",
                    "select": {"name": "クトゥルフ神話TRPG"},
                },
                "PL人数": {
                    "type": "number",
                    "number": 1,
                },
                "所要時間": {
                    "type": "number",
                    "number": 1,
                },
                "概要": {
                    "type": "rich_text",
                    "rich_text": [{"plain_text": "対話型タイマンシナリオ。"}],
                },
                "あらすじ": {
                    "type": "rich_text",
                    "rich_text": [{"plain_text": "目を覚ますと、見知らぬ病室にいた。"}],
                },
                "タグ": {
                    "type": "multi_select",
                    "multi_select": [
                        {"name": "クトゥルフ"},  # CoC に正規化されるべき
                        {"name": "通過済み"},    # 通過済 に正規化されるべき
                        {"name": "GM可"},
                        {"name": "タイマン"},    # ローカルタグとして登録されるべき
                    ],
                },
                "販売URL": {
                    "type": "url",
                    "url": "https://dizm.booth.pm/items/9999999",
                },
                "表紙": {
                    "type": "files",
                    "files": [
                        {
                            "type": "file",
                            "name": "katashiro_cover.jpg",
                            "file": {"url": "https://files.example.com/covers/katashiro.jpg"},
                        }
                    ],
                },
            },
        }

    @classmethod
    def tearDownClass(cls):
        app_settings.SETTINGS_FILE = cls.original_settings_file
        app_settings._settings_instance = None
        try:
            cls.db.conn.close()
        except Exception:
            pass
        shutil.rmtree(cls.tmp_dir, ignore_errors=True)

    def test_01_parse_notion_page_fields_and_cover(self):
        """NotionページJSONからシナリオ名・表紙URL・タグデータが正しく切り分けられること"""
        mapping = notion_sync.guess_mapping(self.mock_schema)
        self.assertEqual(mapping.get("title"), "シナリオ名")
        self.assertEqual(mapping.get("tags"), "タグ")
        self.assertEqual(mapping.get("system_name"), "システム")
        self.assertEqual(mapping.get("players_text"), "PL人数")
        self.assertEqual(mapping.get("duration_text"), "所要時間")
        self.assertEqual(mapping.get("source_url"), "販売URL")

        # 1件目の切り分け検証
        vals_1 = notion_sync.page_values(self.mock_page_1, mapping, self.mock_schema)
        self.assertEqual(vals_1["title"], "狂気山脈 〜邪神の山嶺〜")
        self.assertEqual(vals_1["title_kana"], "きょうきさんみゃく")
        self.assertEqual(vals_1["author"], "まだら牛")
        self.assertEqual(vals_1["system_name"], "クトゥルフ神話TRPG")
        self.assertEqual(vals_1["players_text"], "4人")
        self.assertEqual(vals_1["duration_text"], "6時間")
        self.assertEqual(vals_1["tags"], ["CoC", "未通過", "山岳ホラー", "秘匿HO"])
        self.assertEqual(
            notion_sync.page_cover_url(self.mock_page_1),
            "https://images.example.com/covers/kyoki_sanmyaku.jpg",
        )

        # 2件目の切り分け検証（files型プロパティ「表紙」からの画像URL抽出）
        vals_2 = notion_sync.page_values(self.mock_page_2, mapping, self.mock_schema)
        self.assertEqual(vals_2["title"], "カタシロ")
        self.assertEqual(vals_2["tags"], ["クトゥルフ", "通過済み", "GM可", "タイマン"])
        self.assertEqual(
            notion_sync.page_cover_url(self.mock_page_2),
            "https://files.example.com/covers/katashiro.jpg",
        )

    def test_02_import_from_notion_registers_into_db(self):
        """import_from_notion でシナリオ名・表紙バイナリ・タグがDBへ正しく登録されること"""
        mock_client = MagicMock()
        mock_client.schema.return_value = self.mock_schema
        mock_client.query_all.return_value = [self.mock_page_1, self.mock_page_2]

        def fake_download(url):
            if "kyoki_sanmyaku" in url:
                return self.cover_bytes_1
            if "katashiro" in url:
                return self.cover_bytes_2
            raise ValueError(f"Unexpected URL: {url}")

        mock_client.download.side_effect = fake_download

        imported_ids = notion_sync.import_from_notion(
            db=self.db,
            client=mock_client,
            data_source_id="8f2c3d4e-5f6a-7b8c-9d0e-1f2a3b4c5d6e",
        )
        self.assertEqual(len(imported_ids), 2)

        # --- 1件目のDB登録検証 ---
        item_1 = self.db.get_item(imported_ids[0])
        self.assertIsNotNone(item_1)
        # (id, file_path, title, system_name, players_text, duration_text, overview, synopsis, thumbnail, favorite, bookmarked)
        self.assertEqual(item_1[2], "狂気山脈 〜邪神の山嶺〜")
        self.assertEqual(item_1[3], "クトゥルフ神話TRPG")
        self.assertEqual(item_1[4], "4人")
        self.assertEqual(item_1[5], "6時間")
        self.assertEqual(item_1[6], "南極最高峰に挑む登山家たちの過酷な挑戦。")
        self.assertEqual(item_1[7], "1930年代、南極大陸。前人未到の山脈へ挑む。")
        self.assertEqual(item_1[8], self.cover_bytes_1)  # 表紙バイナリが一致すること
        self.assertEqual(self.db.get_author(imported_ids[0]), "まだら牛")
        self.assertEqual(self.db.get_title_kana(imported_ids[0]), "きょうきさんみゃく")
        self.assertEqual(self.db.get_source_url(imported_ids[0]), "https://dappleox.booth.pm/items/1234567")

        # 1件目のタグ（グローバルタグとローカルタグの切り分け）検証
        global_tags_1 = [t[1] for t in self.db.get_item_tags(imported_ids[0], is_global=True)]
        local_tags_1 = [t[1] for t in self.db.get_item_tags(imported_ids[0], is_global=False)]
        self.assertCountEqual(global_tags_1, ["CoC", "未通過"])
        self.assertCountEqual(local_tags_1, ["山岳ホラー", "秘匿HO"])

        # --- 2件目のDB登録検証 ---
        item_2 = self.db.get_item(imported_ids[1])
        self.assertIsNotNone(item_2)
        self.assertEqual(item_2[2], "カタシロ")
        self.assertEqual(item_2[8], self.cover_bytes_2)  # filesプロパティ由来の表紙バイナリが一致すること

        # 2件目のタグ（「クトゥルフ」→「CoC」、「通過済み」→「通過済み」への正規化、およびローカルタグ「タイマン」）
        global_tags_2 = [t[1] for t in self.db.get_item_tags(imported_ids[1], is_global=True)]
        local_tags_2 = [t[1] for t in self.db.get_item_tags(imported_ids[1], is_global=False)]
        self.assertCountEqual(global_tags_2, ["CoC", "通過済み", "GM可"])
        self.assertCountEqual(local_tags_2, ["タイマン"])

    def test_03_notion_sync_worker_end_to_end_and_detail_dialog(self):
        """NotionSyncWorker経由での同期と、詳細画面での表示（シナリオ名・表紙・タグ・Boothリンク）を検証"""
        # 設定ファイルにトークンとデータベースIDを保存
        app_settings.save(
            {
                "notion_api_key": "ntn_dummy_secret_token_12345",
                "notion_database_id": "8f2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e",
            }
        )

        # Notion上で1件目のタイトルとタグが更新されたケースをシミュレート
        updated_page_1 = dict(self.mock_page_1)
        updated_props = dict(self.mock_page_1["properties"])
        updated_props["タグ"] = {
            "type": "multi_select",
            "multi_select": [
                {"name": "CoC"},
                {"name": "通過済み"},
                {"name": "山岳ホラー"},
                {"name": "神話生物"},
            ],
        }
        updated_page_1["properties"] = updated_props

        with patch("notion_sync.NotionClient") as MockClientCls:
            instance = MockClientCls.return_value
            instance.data_sources.return_value = ("TRPG書架", [("8f2c3d4e-5f6a-7b8c-9d0e-1f2a3b4c5d6e", "Main")])
            instance.schema.return_value = self.mock_schema
            instance.query_all.return_value = [updated_page_1, self.mock_page_2]
            instance.download.side_effect = lambda url: (
                self.cover_bytes_1 if "kyoki_sanmyaku" in url else self.cover_bytes_2
            )

            worker = NotionSyncWorker(self.db)
            results = []
            worker.finished_all.connect(lambda s, f, err: results.append((s, f, err)))
            worker.run()

        self.assertEqual(len(results), 1)
        success_count, fail_count, err_msg = results[0]
        self.assertEqual(err_msg, "")
        self.assertEqual(fail_count, 0)
        self.assertEqual(success_count, 2)

        # 重複登録されず全2件のままであることを確認
        all_items = self.db.get_items()
        self.assertEqual(len(all_items), 2)

        # 更新されたタグが反映されていることを確認
        items_by_title = {it[2]: it for it in all_items}
        kyoki_id = items_by_title["狂気山脈 〜邪神の山嶺〜"][0]
        g_tags = [t[1] for t in self.db.get_item_tags(kyoki_id, is_global=True)]
        l_tags = [t[1] for t in self.db.get_item_tags(kyoki_id, is_global=False)]
        self.assertCountEqual(g_tags, ["CoC", "通過済み"])
        self.assertCountEqual(l_tags, ["山岳ホラー", "神話生物"])

        # 詳細ダイアログを開いてシナリオ名・タグ・情報元リンク・表紙が表示されるか確認
        dlg = ItemDetailDialog(kyoki_id, self.db, None, item_ids=[kyoki_id])
        dlg.resize(980, 720)
        dlg.show()
        self.app.processEvents()

        self.assertEqual(dlg.view_labels["title"].text(), "狂気山脈 〜邪神の山嶺〜")
        self.assertIsNotNone(dlg.cover_label.pixmap())
        self.assertFalse(dlg.cover_label.pixmap().isNull())
        self.assertTrue(dlg.file_link_label.isHidden())  # notion:// 識別子はローカルファイルリンクとして表示しない
        self.assertFalse(dlg.url_label.isHidden())
        self.assertEqual(dlg.url_label.text(), "🔗  Booth")
        self.assertIn("CoC", dlg.tags_box.text())
        self.assertIn("山岳ホラー", dlg.tags_box.text())
        dlg.close()

    def test_04_export_properties_tailored_to_table_schema(self):
        """書き出し時にNotion側の様々なテーブル構造（列の型・有無）に沿ってデータが整形されること"""
        item_values = {
            "title": "誰がロックを殺すのか？",
            "title_kana": "だれがろっくをころすのか",
            "author": "角刈りジョニー",
            "system_name": "クトゥルフ神話TRPG",
            "players_text": "3〜4人",
            "duration_text": "8.5時間",
            "overview": "音楽バンドをテーマにした現代CoCシナリオ。",
            "synopsis": "あなたたちは人気ロックバンドのメンバーだ。",
            "tags": ["CoC", "未通過", "音楽", "秘匿HO"],
            "source_url": "https://booth.pm/ja/items/5555555",
            "file_path": r"C:\Scenarios\rock.zip",
        }

        # パターンA: PL人数・所要時間が number 型、タグが multi_select 型、表紙が files 型のテーブル
        schema_a = self.mock_schema
        mapping_a = notion_sync.guess_mapping(schema_a)
        props_a = notion_sync.build_properties(
            item_values, mapping_a, schema_a, cover_upload_id="file_upload_id_999"
        )

        self.assertEqual(
            props_a["シナリオ名"],
            {"title": [{"type": "text", "text": {"content": "誰がロックを殺すのか？"}}]},
        )
        self.assertEqual(props_a["システム"], {"select": {"name": "クトゥルフ神話TRPG"}})
        self.assertEqual(props_a["PL人数"], {"number": 3})       # "3〜4人" から先頭数値 3 に自動変換
        self.assertEqual(props_a["所要時間"], {"number": 8.5})   # "8.5時間" から 8.5 に自動変換
        self.assertEqual(
            props_a["タグ"],
            {
                "multi_select": [
                    {"name": "CoC"},
                    {"name": "未通過"},
                    {"name": "音楽"},
                    {"name": "秘匿HO"},
                ]
            },
        )
        self.assertEqual(
            props_a["表紙"],
            {
                "files": [
                    {
                        "type": "file_upload",
                        "name": "cover.jpg",
                        "file_upload": {"id": "file_upload_id_999"},
                    }
                ]
            },
        )
        # schema_a に存在しない「ファイルの場所」列は送出されないこと
        self.assertNotIn("ファイルの場所", props_a)

        # パターンB: PL人数が rich_text、システムが status、タグが select（単一選択）のミニマルなテーブル
        schema_b = {
            "Title": "title",
            "ルール": "status",
            "プレイヤー人数": "rich_text",
            "ラベル": "select",
        }
        mapping_b = notion_sync.guess_mapping(schema_b)
        props_b = notion_sync.build_properties(item_values, mapping_b, schema_b)

        self.assertEqual(
            props_b["Title"],
            {"title": [{"type": "text", "text": {"content": "誰がロックを殺すのか？"}}]},
        )
        self.assertEqual(props_b["ルール"], {"status": {"name": "クトゥルフ神話TRPG"}})
        self.assertEqual(
            props_b["プレイヤー人数"],
            {"rich_text": [{"type": "text", "text": {"content": "3〜4人"}}]},
        )
        # select 型にリストを渡しても "['CoC', ...]" にならず綺麗に結合されること
        self.assertEqual(props_b["ラベル"], {"select": {"name": "CoC・未通過・音楽・秘匿HO"}})

    def test_05_worker_exports_new_local_item_with_cover_and_tags_to_notion(self):
        """ローカルDBで新規追加したシナリオが、NotionSyncWorkerでテーブル構造に沿って表紙・タグごと書き出されること"""
        cover_bytes_3 = _make_dummy_image_bytes(color=(40, 120, 60))
        new_local_id = self.db.save_item(
            file_path=os.path.join(self.tmp_dir, "誰がロックを殺すのか.zip"),
            title="誰がロックを殺すのか？",
            system_name="クトゥルフ神話TRPG",
            players_text="4人",
            duration_text="8時間",
            overview="バンド×秘匿HOシナリオ",
            synopsis="ロックバンドの運命やいかに。",
            thumbnail_bytes=cover_bytes_3,
        )
        self.db.set_source_url(new_local_id, "https://booth.pm/ja/items/5555555")
        self.db.add_tags_to_item(new_local_id, ["CoC", "未通過", "音楽", "秘匿HO"])

        with patch("notion_sync.NotionClient") as MockClientCls:
            instance = MockClientCls.return_value
            instance.data_sources.return_value = ("TRPG書架", [("8f2c3d4e-5f6a-7b8c-9d0e-1f2a3b4c5d6e", "Main")])
            instance.schema.return_value = self.mock_schema
            instance.query_all.return_value = [self.mock_page_1, self.mock_page_2]
            instance.download.side_effect = lambda url: (
                self.cover_bytes_1 if "kyoki_sanmyaku" in url else self.cover_bytes_2
            )
            instance.upload_file.return_value = "uploaded_cover_file_id_777"
            instance.create_page.return_value = {"id": "99999999-8888-7777-6666-555555555555"}

            worker = NotionSyncWorker(self.db)
            results = []
            worker.finished_all.connect(lambda s, f, err: results.append((s, f, err)))
            worker.run()

            # 1. 表紙バイナリが upload_file でアップロードされたこと
            instance.upload_file.assert_called_once_with(
                cover_bytes_3, filename="cover.jpg", content_type="image/jpeg"
            )

            # 2. create_page がスキーマに沿った properties と cover_upload_id で呼ばれたこと
            instance.create_page.assert_called_once()
            call_args, call_kwargs = instance.create_page.call_args
            ds_arg, props_arg = call_args[0], call_args[1]
            self.assertEqual(ds_arg, "8f2c3d4e-5f6a-7b8c-9d0e-1f2a3b4c5d6e")
            self.assertEqual(call_kwargs.get("cover_upload_id"), "uploaded_cover_file_id_777")
            self.assertEqual(
                props_arg["シナリオ名"],
                {"title": [{"type": "text", "text": {"content": "誰がロックを殺すのか？"}}]},
            )
            self.assertEqual(props_arg["PL人数"], {"number": 4})
            self.assertEqual(props_arg["所要時間"], {"number": 8})
            tag_names_sent = [o["name"] for o in props_arg["タグ"]["multi_select"]]
            self.assertCountEqual(tag_names_sent, ["CoC", "未通過", "音楽", "秘匿HO"])
            self.assertEqual(
                props_arg["表紙"]["files"][0]["file_upload"]["id"],
                "uploaded_cover_file_id_777",
            )

        # 3. DB側に発行された notion_page_id と notion_cover_hash が保存されていること
        exported_rows = [it for it in self.db.items_for_notion() if it["id"] == new_local_id]
        self.assertEqual(len(exported_rows), 1)
        self.assertEqual(exported_rows[0]["notion_page_id"], "99999999-8888-7777-6666-555555555555")
        self.assertEqual(
            exported_rows[0]["notion_cover_hash"],
            notion_sync.compute_cover_hash(cover_bytes_3),
        )

    def test_06_api_request_interval_default_and_settings_dialog_persistence(self):
        """API利用間隔の初期値がNotion API（無料枠）想定の0.5秒であり、設定ダイアログから変更・保存・反映できること"""
        from gui_qt.dialogs.settings_dialog import SettingsDialog

        # 1. 初期値が 0.5 秒であることの確認
        self.assertEqual(app_settings.DEFAULT_API_INTERVAL, 0.5)
        self.assertEqual(app_settings.get_api_interval(), 0.5)

        default_client = notion_sync.NotionClient("ntn_dummy")
        self.assertEqual(default_client.request_interval, 0.5)

        # 2. SettingsDialog を開いた際に初期値 0.5 秒および初期取り込み上限10件が表示され、変更して保存すると反映されること
        dlg = SettingsDialog(self.db, None)
        self.assertAlmostEqual(dlg.api_interval_spin.value(), 0.5, places=2)
        self.assertEqual(dlg.notion_limit_spin.value(), 10)

        dlg.api_interval_spin.setValue(1.5)
        dlg.notion_limit_spin.setValue(25)
        with patch("gui_qt.dialogs.settings_dialog.QMessageBox.information"):
            dlg._save_settings()
        dlg.close()

        self.assertAlmostEqual(app_settings.get_api_interval(), 1.5, places=2)
        self.assertEqual(app_settings.get_notion_import_limit(), 25)
        updated_client = notion_sync.NotionClient("ntn_dummy")
        self.assertAlmostEqual(updated_client.request_interval, 1.5, places=2)

        # 3. 0（無制限）への変更と保存の検証
        dlg2 = SettingsDialog(self.db, None)
        self.assertEqual(dlg2.notion_limit_spin.value(), 25)
        dlg2.notion_limit_spin.setValue(0)
        with patch("gui_qt.dialogs.settings_dialog.QMessageBox.information"):
            dlg2._save_settings()
        dlg2.close()
        self.assertEqual(app_settings.get_notion_import_limit(), 0)

    def test_07_notion_client_query_all_limit(self):
        """NotionClient.query_all で limit=10 を指定した際、10件に達した時点で取得が打ち切られること"""
        client = notion_sync.NotionClient("dummy_token", request_interval=0)
        
        # 1回目のレスポンス（6件、has_more=True）
        res1 = {
            "results": [{"object": "page", "id": f"p-{i}", "in_trash": False, "archived": False} for i in range(1, 7)],
            "has_more": True,
            "next_cursor": "cursor_2",
        }
        # 2回目のレスポンス（6件、has_more=True）
        res2 = {
            "results": [{"object": "page", "id": f"p-{i}", "in_trash": False, "archived": False} for i in range(7, 13)],
            "has_more": True,
            "next_cursor": "cursor_3",
        }

        call_count = [0]
        def fake_request(method, path, body=None, raw=None, content_type=None):
            call_count[0] += 1
            if call_count[0] == 1:
                self.assertEqual(body.get("page_size"), 10)
                return res1
            elif call_count[0] == 2:
                # 6件取得済みなので残り4件要求
                self.assertEqual(body.get("page_size"), 4)
                return res2
            else:
                self.fail("余計なリクエストが発生しました")

        with patch.object(client, "request", side_effect=fake_request):
            pages = client.query_all("dummy_db_id", limit=10)

        self.assertEqual(len(pages), 10)
        self.assertEqual([p["id"] for p in pages], [f"p-{i}" for i in range(1, 11)])
        self.assertEqual(call_count[0], 2)

    def test_08_import_from_notion_limits_to_10_by_default(self):
        """import_from_notion がデフォルトで limit=10 を指定し、最大10件のみ取り込むこと"""
        mock_client = MagicMock()
        mock_client.schema.return_value = self.mock_schema
        # 15件のページを返す
        fake_pages = [
            {
                "id": f"dummy-page-{i}",
                "properties": {
                    "シナリオ名": {"title": [{"plain_text": f"シナリオ {i}"}]},
                },
            }
            for i in range(1, 16)
        ]
        mock_client.query_all.return_value = fake_pages
        mock_client.download.return_value = None

        imported_ids = notion_sync.import_from_notion(
            db=self.db,
            client=mock_client,
            data_source_id="dummy_ds_id",
        )
        # query_all に limit=10 が渡されていること
        mock_client.query_all.assert_called_with("dummy_ds_id", limit=10)
        # 返り値が15件あっても 10件に制限されてDB登録されること
        self.assertEqual(len(imported_ids), 10)

    def test_09_notion_sync_worker_limits_import_to_10(self):
        """NotionSyncWorker が Notion からの取り込み時に limit=10 を指定して最大10件に限定すること"""
        from gui_qt.dialogs.notion_sync_dialog import NotionSyncWorker

        app_settings.save(
            {
                "notion_api_key": "ntn_dummy_secret_token_12345",
                "notion_database_id": "8f2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e",
                "notion_import_limit": 10,
            }
        )

        isolated_db = Database(os.path.join(self.tmp_dir, "test_isolated_worker_10.db"))

        with patch("notion_sync.NotionClient") as MockClientClass:
            instance = MockClientClass.return_value
            instance.data_sources.return_value = ("TestDB", [("src_1", "TestDB")])
            instance.schema.return_value = self.mock_schema
            fake_pages = [
                {
                    "id": f"sync-page-{i}",
                    "properties": {
                        "シナリオ名": {"type": "title", "title": [{"plain_text": f"同期シナリオ {i}"}]},
                    },
                }
                for i in range(1, 16)
            ]
            instance.query_all.return_value = fake_pages
            instance.download.return_value = None

            worker = NotionSyncWorker(isolated_db)
            results = []
            worker.finished_all.connect(lambda s, f, err: results.append((s, f, err)))
            worker.run()

            # query_all が limit=10 で呼ばれていること
            instance.query_all.assert_called_with("src_1", limit=10)
            self.assertEqual(len(results), 1)
            # 15件返されても最大10件のみインポートされること
            self.assertEqual(results[0][0], 10)
            self.assertEqual(len(isolated_db.get_items()), 10)

    def test_10_notion_import_limit_setting_and_unlimited_zero(self):
        """Notion取り込み件数設定で0を指定した際に無制限(limit=None)としてクエリされること"""
        from gui_qt.dialogs.notion_sync_dialog import NotionSyncWorker

        app_settings.save(
            {
                "notion_api_key": "ntn_dummy_token",
                "notion_database_id": "8f2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e",
                "notion_import_limit": 0,
            }
        )
        self.assertEqual(app_settings.get_notion_import_limit(), 0)

        isolated_db = Database(os.path.join(self.tmp_dir, "test_isolated_worker_0.db"))

        with patch("notion_sync.NotionClient") as MockClientClass:
            instance = MockClientClass.return_value
            instance.data_sources.return_value = ("TestDB", [("src_1", "TestDB")])
            instance.schema.return_value = self.mock_schema
            instance.query_all.return_value = []

            worker = NotionSyncWorker(isolated_db)
            worker.run()

            # limit=0 のときは query_all に limit=None（無制限）が渡されること
            instance.query_all.assert_called_with("src_1", limit=None)

    def test_11_notion_sync_worker_skip_same_last_edited_time(self):
        """NotionページとDBの notion_last_edited_time が同一の場合は更新処理がスキップされること"""
        from gui_qt.dialogs.notion_sync_dialog import NotionSyncWorker

        app_settings.save(
            {
                "notion_api_key": "ntn_dummy_token",
                "notion_database_id": "8f2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e",
                "notion_import_limit": 10,
            }
        )

        test_db = Database(os.path.join(self.tmp_dir, "test_skip_same_time.db"))
        # 1回目の登録（last_edited_time = "2026-10-18T00:00:00.000Z"）
        edit_time_v1 = "2026-10-18T00:00:00.000Z"
        page_id = "test-page-skip-001"
        test_db.save_or_update_from_notion(
            page_id,
            {"title": "スキップ検証シナリオ", "author": "既存作者"},
            last_edited_time=edit_time_v1,
        )

        with patch("notion_sync.NotionClient") as MockClientClass:
            instance = MockClientClass.return_value
            instance.data_sources.return_value = ("TestDB", [("src_1", "TestDB")])
            instance.schema.return_value = self.mock_schema
            page_same_time = {
                "id": page_id,
                "last_edited_time": edit_time_v1,  # 同一日時
                "properties": {
                    "シナリオ名": {"type": "title", "title": [{"plain_text": "変更されないタイトル"}]},
                },
            }
            instance.query_all.return_value = [page_same_time]

            worker = NotionSyncWorker(test_db)
            worker.run()

            # 同一日時のためダウンロードは呼ばれず、DBも更新されないこと
            instance.download.assert_not_called()
            item = test_db.find_existing_item_for_notion(page_id=page_id)
            self.assertEqual(item["title"], "スキップ検証シナリオ")

    def test_12_notion_sync_worker_diff_resolution_and_selective_apply(self):
        """Notion側の更新または同一タイトルのデータ検出時に比較選択ダイアログのシグナルが飛び、選択項目が反映されること"""
        from gui_qt.dialogs.notion_sync_dialog import NotionSyncWorker

        app_settings.save(
            {
                "notion_api_key": "ntn_dummy_token",
                "notion_database_id": "8f2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e",
                "notion_import_limit": 10,
            }
        )

        test_db = Database(os.path.join(self.tmp_dir, "test_diff_resolve.db"))
        # 手元データ（未連携、タイトル「古の呪文」）
        item_id = test_db.save_item(
            file_path="local://sample_spell.pdf",
            title="古の呪文",
            system_name="クトゥルフ神話TRPG",
            players_text="3人",
            duration_text="4時間",
            overview="手元の概要",
            synopsis="手元のあらすじ",
            thumbnail_bytes=None,
        )
        with test_db.conn:
            test_db.conn.execute("UPDATE items SET author = ? WHERE id = ?;", ("手元の作者", item_id))

        with patch("notion_sync.NotionClient") as MockClientClass:
            instance = MockClientClass.return_value
            instance.data_sources.return_value = ("TestDB", [("src_1", "TestDB")])
            instance.schema.return_value = self.mock_schema
            new_page = {
                "id": "notion-spell-page-999",
                "last_edited_time": "2026-10-18T05:00:00.000Z",
                "properties": {
                    "シナリオ名": {"type": "title", "title": [{"plain_text": "古の呪文"}]},
                    "作者": {"type": "rich_text", "rich_text": [{"plain_text": "Notion側の新しい作者"}]},
                    "概要": {"type": "rich_text", "rich_text": [{"plain_text": "Notion側の新しい概要"}]},
                },
            }
            instance.query_all.return_value = [new_page]
            instance.download.return_value = None

            worker = NotionSyncWorker(test_db)
            worker.has_diff_receiver = True

            # シグナルハンドラをシミュレート（作者のみ採用、概要は不採用）
            signal_called = [False]
            def fake_on_diff(curr_dict, notion_dict, queue_and_id):
                signal_called[0] = True
                res_q, it_id = queue_and_id
                self.assertEqual(it_id, item_id)
                self.assertEqual(curr_dict["author"], "手元の作者")
                self.assertEqual(notion_dict["author"], "Notion側の新しい作者")
                # 「作者」のみ反映を選択
                res_q.put({"action": "apply", "selected_fields": {"author"}})

            worker.request_diff_resolution.connect(fake_on_diff)
            worker.run()

            self.assertTrue(signal_called[0])
            # 反映結果の検証
            updated = test_db.get_item_detail_dict(item_id)
            self.assertEqual(updated["author"], "Notion側の新しい作者")  # 反映された
            self.assertEqual(updated["overview"], "手元の概要")            # 反映されず手元のまま保持
            self.assertEqual(updated["notion_page_id"], "notion-spell-page-999")
            self.assertEqual(updated["notion_last_edited_time"], "2026-10-18T05:00:00.000Z")

    def test_audit_notion_diff_and_single_actions(self):
        """Notionとローカルデータの突合照合（不足分・差異リストアップ）および個別登録・取り込みの検証"""
        test_db = Database(os.path.join(self.tmp_dir, "test_audit_diff.db"))

        # 1. ローカルアイテムの作成
        # a) ローカルのみに存在
        id_local_only = test_db.save_item(
            file_path="local://local_only.pdf",
            title="孤高の古書",
            system_name="クトゥルフ神話TRPG",
            players_text="2人",
            duration_text="3時間",
            overview="ローカルのみの概要",
            synopsis="手元のあらすじ",
            thumbnail_bytes=None,
        )

        # b) 両方に存在するが、項目欠落・差異がある
        id_partial = test_db.save_item(
            file_path="local://partial_diff.pdf",
            title="霧深き館",
            system_name="エモクロアTRPG",
            players_text=None,
            duration_text=None,
            overview="ローカルの概要あり",
            synopsis=None,
            thumbnail_bytes=self.cover_bytes_1,
        )
        test_db.set_notion_link(id_partial, "notion-pid-partial")

        # c) 完全一致（差異なし）
        id_identical = test_db.save_item(
            file_path="local://identical.pdf",
            title="完全なる調和",
            system_name="クトゥルフ神話TRPG",
            players_text=None,
            duration_text=None,
            overview="共通の概要",
            synopsis=None,
            thumbnail_bytes=None,
        )
        test_db.set_notion_link(id_identical, "notion-pid-identical")


        # 2. 模擬 Notion ページデータ
        # - partial: 作者・時間があるが概要がない、表紙画像なし
        page_partial = {
            "id": "notion-pid-partial",
            "last_edited_time": "2026-10-18T06:00:00.000Z",
            "properties": {
                "シナリオ名": {"type": "title", "title": [{"plain_text": "霧深き館"}]},
                "システム": {"type": "select", "select": {"name": "エモクロアTRPG"}},
                "作者": {"type": "rich_text", "rich_text": [{"plain_text": "霧中人"}]},
                "所要時間": {"type": "number", "number": 180},
                "概要": {"type": "rich_text", "rich_text": []},  # Notion側は欠落
            },
        }

        # - identical: 全て一致
        page_identical = {
            "id": "notion-pid-identical",
            "last_edited_time": "2026-10-18T06:00:00.000Z",
            "properties": {
                "シナリオ名": {"type": "title", "title": [{"plain_text": "完全なる調和"}]},
                "システム": {"type": "select", "select": {"name": "クトゥルフ神話TRPG"}},
                "概要": {"type": "rich_text", "rich_text": [{"plain_text": "共通の概要"}]},
            },
        }

        # - remote_only: Notion側にのみ存在（手元にない）
        page_remote_only = {
            "id": "notion-pid-remote-only",
            "last_edited_time": "2026-10-18T06:00:00.000Z",
            "properties": {
                "シナリオ名": {"type": "title", "title": [{"plain_text": "遥かなる星辰"}]},
                "システム": {"type": "select", "select": {"name": "シノビガミ"}},
                "作者": {"type": "rich_text", "rich_text": [{"plain_text": "星詠み"}]},
            },
        }

        mapping = {
            "title": "シナリオ名",
            "system_name": "システム",
            "author": "作者",
            "duration_text": "所要時間",
            "overview": "概要",
            "cover": "表紙",
        }

        client = MagicMock()
        client.query_all.return_value = [page_partial, page_identical, page_remote_only]

        # 3. 差異・不足照合の実行
        progress_msgs = []
        result = notion_sync.audit_notion_diff(
            test_db,
            client,
            "data_source_123",
            mapping=mapping,
            schema=self.mock_schema,
            progress_callback=lambda m: progress_msgs.append(m),
        )

        # 照合結果の検証
        self.assertGreater(len(progress_msgs), 0)

        # 手元のみ
        local_titles = [it["title"] for it in result["local_only"]]
        self.assertIn("孤高の古書", local_titles)
        self.assertNotIn("霧深き館", local_titles)
        self.assertNotIn("完全なる調和", local_titles)

        # Notionのみ
        remote_titles = [it["title"] for it in result["notion_only"]]
        self.assertIn("遥かなる星辰", remote_titles)
        self.assertNotIn("霧深き館", remote_titles)
        self.assertNotIn("完全なる調和", remote_titles)

        # 項目差異・不足
        partial_titles = [it["title"] for it in result["field_lacking"]]
        self.assertIn("霧深き館", partial_titles)
        self.assertNotIn("完全なる調和", partial_titles)

        diff_item = next(it for it in result["field_lacking"] if it["title"] == "霧深き館")
        self.assertIn("作者", diff_item["local_missing"])       # Notionにある作者がローカルにない
        self.assertIn("所要時間", diff_item["local_missing"])   # Notionにある時間がローカルにない
        self.assertIn("概要", diff_item["notion_missing"])      # ローカルにある概要がNotionにない
        self.assertIn("表紙画像", diff_item["notion_missing"])  # ローカルにある表紙がNotionにない


        # 4. 手元のみのシナリオを単一でNotionへ登録（export_single_item_to_notion）
        client.create_page.return_value = {"id": "new-notion-pid-book"}
        exp_pid = notion_sync.export_single_item_to_notion(
            test_db,
            client,
            "data_source_123",
            id_local_only,
            mapping=mapping,
            schema=self.mock_schema,
        )
        self.assertEqual(exp_pid, "new-notion-pid-book")
        it_after_export = test_db.get_item_detail_dict(id_local_only)
        self.assertEqual(it_after_export["notion_page_id"], "new-notion-pid-book")

        # 5. Notionのみのシナリオを手元へ単一で取り込み（import_single_page_from_notion）
        new_imported_id = notion_sync.import_single_page_from_notion(
            test_db,
            client,
            page_remote_only,
            mapping=mapping,
            schema=self.mock_schema,
        )
        self.assertIsNotNone(new_imported_id)
        imported_item = test_db.get_item_detail_dict(new_imported_id)
        self.assertEqual(imported_item["title"], "遥かなる星辰")
        self.assertEqual(imported_item["system_name"], "シノビガミ")
        self.assertEqual(imported_item["author"], "星詠み")
        self.assertEqual(imported_item["notion_page_id"], "notion-pid-remote-only")


    def test_notion_diff_dialog_instantiation(self):
        """NotionDiffDialog の初期化とUI構築が正常に動作することの検証"""
        from gui_qt.dialogs.notion_diff_dialog import NotionDiffDialog

        test_db = Database(os.path.join(self.tmp_dir, "test_diff_dlg.db"))
        dlg = NotionDiffDialog(test_db)
        self.assertIsNotNone(dlg.tabs)
        self.assertEqual(dlg.tabs.count(), 3)
        self.assertIn("手元のみ", dlg.tabs.tabText(0))
        self.assertIn("Notionのみ", dlg.tabs.tabText(1))
        self.assertIn("項目不足", dlg.tabs.tabText(2))
        dlg.close()

    def test_notion_audit_worker_thread_safety(self):
        """NotionAuditWorker がバックグラウンドスレッドで SQLite エラーを起こさず正常終了することの検証"""
        from gui_qt.dialogs.notion_diff_dialog import NotionAuditWorker
        from app_settings import Settings

        # 設定ファイルの模擬
        settings = Settings(app_settings.SETTINGS_FILE)
        settings.set_secret("notion", "token", "ntn_mock_token_for_audit")
        settings.set("notion", "database_id", "3efa0f785c9f80788273fde81b4ddeaa")

        test_db = Database(os.path.join(self.tmp_dir, "test_audit_worker_thread.db"))
        test_db.save_item(
            file_path="local://thread_item.pdf",
            title="星辰の書",
            system_name="クトゥルフ神話TRPG",
            players_text="3人",
            duration_text="4時間",
            overview="概要テスト",
            synopsis="あらすじテスト",
            thumbnail_bytes=None,
        )

        with patch("notion_sync.NotionClient") as MockClientClass:
            mock_client = MockClientClass.return_value
            mock_client.data_sources.return_value = ("TRPGリスト", [("src_dummy", "TRPGリスト")])
            mock_client.schema.return_value = self.mock_schema
            mock_client.query_all.return_value = []

            worker = NotionAuditWorker(test_db)
            results = []
            errors = []

            worker.finished.connect(lambda res: results.append(res))
            worker.error.connect(lambda err: errors.append(err))

            worker.start()
            self.assertTrue(worker.wait(3000))
            self.app.processEvents()

            self.assertEqual(len(errors), 0, f"Worker returned error: {errors}")
            self.assertEqual(len(results), 1)

            diff_res = results[0]
            self.assertEqual(diff_res.get("local_total"), 1)
            self.assertEqual(diff_res.get("notion_total"), 0)
            self.assertEqual(len(diff_res.get("local_only")), 1)

    def test_notion_diff_dialog_resolve_single_diff(self):
        """NotionDiffDialog の「対比・採否選択」ボタン経由で WebInfoComparisonDialog が起動し、正常反映されることの検証"""
        from gui_qt.dialogs.notion_diff_dialog import NotionDiffDialog
        from PySide6.QtWidgets import QDialog

        test_db = Database(os.path.join(self.tmp_dir, "test_diff_resolve_dlg.db"))
        item_id = test_db.save_item(
            file_path="local://diff_resolve.pdf",
            title="霧深き館",
            system_name="エモクロアTRPG",
            players_text="2人",
            duration_text=None,
            overview="ローカルの概要",
            synopsis=None,
            thumbnail_bytes=None,
        )

        with patch.object(NotionDiffDialog, "_start_audit", lambda self: None):
            dlg = NotionDiffDialog(test_db)
            diff_entry = {
                "item_id": item_id,
                "page_id": "notion-pid-resolve-1",
                "title": "霧深き館",
                "local_item": {
                    "title": "霧深き館",
                    "system_name": "エモクロアTRPG",
                    "players_text": "2人",
                    "duration_text": "",
                    "overview": "ローカルの概要",
                    "synopsis": "",
                    "tags": ["エモクロア"],
                    "thumbnail": None,
                },
                "notion_vals": {
                    "title": "霧深き館",
                    "system_name": "エモクロアTRPG",
                    "players_text": "2人",
                    "duration_text": "120分",
                    "overview": "ローカルの概要",
                    "synopsis": "Notionのあらすじ",
                    "tags": ["エモクロア", "洋館"],
                    "cover_url": None,
                },
            }

            # WebInfoComparisonDialog.exec() をAcceptedとしてモック化
            with patch("gui_qt.dialogs.notion_diff_dialog.WebInfoComparisonDialog") as MockCompClass, \
                 patch("gui_qt.dialogs.notion_diff_dialog.QMessageBox.information") as mock_info, \
                 patch("gui_qt.dialogs.notion_diff_dialog.QMessageBox.warning") as mock_warn:
                mock_comp = MockCompClass.return_value
                mock_comp.exec.return_value = QDialog.Accepted
                mock_comp.edited_in_detail = False
                mock_comp.get_selected_fields.return_value = {"duration", "synopsis"}

                dlg._resolve_single_diff(diff_entry)

                updated = test_db.get_item_detail_dict(item_id)
                self.assertEqual(updated["duration"], "120分")
                self.assertEqual(updated["synopsis"], "Notionのあらすじ")
                self.assertEqual(updated["overview"], "ローカルの概要")
                mock_info.assert_called()

            dlg.close()

    def test_17_notion_tags_and_player_tags_spec(self):
        """Notion取り込み時のタグ登録、および5人以上『5PL以上』・4人以下『4PL』『2PL』の人数タグ仕様の検証"""
        from core.database import generate_player_tags, canonical_tag

        # 1. generate_player_tags の検証（5人以上は「5PL以上」、4人以下は「4PL」「2PL」等）
        self.assertEqual(generate_player_tags("4人"), ["4PL"])
        self.assertEqual(generate_player_tags("2人"), ["2PL"])
        self.assertEqual(generate_player_tags("1人"), ["1PL"])
        self.assertEqual(generate_player_tags("2〜4人"), ["2〜4PL"])
        self.assertEqual(generate_player_tags("5人"), ["5PL以上"])
        self.assertEqual(generate_player_tags("6人"), ["5PL以上"])
        self.assertEqual(generate_player_tags("7人"), ["5PL以上"])
        self.assertEqual(generate_player_tags("PL6人＋GM1人"), ["5PL以上"])
        self.assertEqual(generate_player_tags("6人（GMレス）"), ["GMレス", "5PL以上"])
        self.assertEqual(generate_player_tags("ソロシナリオ"), ["GMレス", "1PL"])

        # 2. canonical_tag による人数タグ表記揺れ正規化
        self.assertEqual(canonical_tag("5PL"), "5PL以上")
        self.assertEqual(canonical_tag("6PL"), "5PL以上")
        self.assertEqual(canonical_tag("7PL"), "5PL以上")
        self.assertEqual(canonical_tag("5｀L以上"), "5PL以上")
        self.assertEqual(canonical_tag("5pl以上"), "5PL以上")
        self.assertEqual(canonical_tag("4PL"), "4PL")
        self.assertEqual(canonical_tag("2pl"), "2PL")
        self.assertEqual(canonical_tag("1PL"), "1PL")

        # 3. Notionから新規取り込み（5人以上マーダーミステリー）
        # Notionのタグ「6PL」が「5PL以上」として登録され、Notionタグがシナリオタグとしてすべて反映されること
        item_id_mm = self.db.save_or_update_from_notion(
            page_id="notion-page-spec-6pl",
            values={
                "title": "幽霊屋敷の密室（マダミス）",
                "system_name": "マーダーミステリー",
                "players_text": "PL6人＋GM1人",
                "tags": ["マダミス", "未通過", "洋館", "6PL"],
            },
        )
        tags_mm = [t[1] for t in self.db.get_item_tags(item_id_mm)]
        self.assertIn("マダミス", tags_mm)
        self.assertIn("未通過", tags_mm)
        self.assertIn("洋館", tags_mm)
        self.assertIn("5PL以上", tags_mm)
        self.assertNotIn("6PL", tags_mm)

        # 4. Notionから新規取り込み（4人CoC）
        # 4人以下は従来通り「4PL」
        item_id_coc = self.db.save_or_update_from_notion(
            page_id="notion-page-spec-4pl",
            values={
                "title": "深海からの呼び声",
                "system_name": "クトゥルフ神話TRPG",
                "players_text": "4人",
                "tags": ["CoC", "通過済み", "深海", "4PL"],
            },
        )
        tags_coc = [t[1] for t in self.db.get_item_tags(item_id_coc)]
        self.assertIn("CoC", tags_coc)
        self.assertIn("通過済み", tags_coc)
        self.assertIn("深海", tags_coc)
        self.assertIn("4PL", tags_coc)
        self.assertNotIn("5PL以上", tags_coc)


if __name__ == "__main__":
    unittest.main()





