"""Notion の通過記録（通過日・GM・PC名・同卓者など）をセッション履歴として取り込む機能の検証テスト
(tests/test_notion_play_log_import.py)

実際の Notion には接続しない（Notion を模した偽のクライアントを使う）。

1. 利用者の Notion データベースと同じ列構成から、通過記録の列を正しく見分けること
   （「同卓者（PC名）」を PC名 と取り違えない・情報元の URL 列をキャラシートと取り違えない）
2. 日付（時刻付き・期間）や、改行で並べた同卓者をセッション履歴の形に直すこと
3. 取り込んだ記録は Notion 側が変わったときだけ書き換え、手元で直した内容を勝手に戻さないこと
4. Notion 側の記録が空になったら取り込んだ記録だけを消し、手元で書いた記録は残すこと
5. 同調で取り込まれ、すでに同調済みで Notion 側が変わっていないページの通過記録も、初回だけ全ページから取り込むこと
6. セッション履歴の画面に GM・キャラクターシートが表示されること
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

import notion_sync
from core.database import Database
import test_notion_background_sync as base

# 利用者の Notion データベース（TRPGリスト）と同じ列構成（API の型名）
USER_SCHEMA = {
    "Name": "title",
    "作者": "rich_text",
    "TAGs": "multi_select",
    "URL": "url",
    "概要": "rich_text",
    "あらすじ": "rich_text",
    "その他": "rich_text",
    "Thumbnail": "files",
    "キャラクター": "files",
    "通過日": "date",
    "GM": "rich_text",
    "PC名": "rich_text",
    "同卓者（PC名）": "rich_text",
    "いあきゃら": "url",
}


def _text(value):
    return {"type": "rich_text", "rich_text": [{"type": "text", "text": {"content": value}, "plain_text": value}]}


def _page(pid, title, edited, **cols):
    props = {"Name": {"type": "title", "title": [{"type": "text", "text": {"content": title}, "plain_text": title}]}}
    for name, value in cols.items():
        props[name] = value
    return {"id": pid, "object": "page", "last_edited_time": edited, "properties": props}


class TestPlayLogColumns(unittest.TestCase):
    def test_01_detects_columns_of_user_database(self):
        mapping = notion_sync.guess_mapping(USER_SCHEMA)
        play = notion_sync.guess_play_log_mapping(USER_SCHEMA, exclude=mapping.values())
        self.assertEqual(play, {
            "session_date": "通過日",
            "party_members": "同卓者（PC名）",
            "gm": "GM",
            "character_name": "PC名",
            "sheet_url": "いあきゃら",
        })
        self.assertEqual(mapping.get("source_url"), "URL")
        # 通過記録の列をシナリオ情報の列として使っていないこと
        self.assertFalse(set(mapping.values()) & set(play.values()), mapping)

    def test_01b_no_play_log_columns(self):
        self.assertEqual(notion_sync.guess_play_log_mapping({"名前": "title", "概要": "rich_text"}), {})

    def test_02_page_values_builds_play_log(self):
        mapping = notion_sync.guess_mapping(USER_SCHEMA)
        page = _page(
            "p1", "影の館", "2026-10-01T00:00:00.000Z",
            **{
                "通過日": {"type": "date", "date": {"start": "2024-05-03T21:00:00.000+09:00", "end": None}},
                "GM": _text("Aさん"),
                "PC名": _text("御手洗 清十郎"),
                "同卓者（PC名）": _text("Bさん（佐藤）\nCさん（鈴木）\n"),
                "いあきゃら": {"type": "url", "url": "https://iachara.com/view/123"},
            },
        )
        vals = notion_sync.page_values(page, mapping, USER_SCHEMA)
        self.assertEqual(vals["play_log"], {
            "session_date": "2024-05-03",
            "gm": "Aさん",
            "character_name": "御手洗 清十郎",
            "party_members": "Bさん（佐藤）、Cさん（鈴木）",
            "sheet_url": "https://iachara.com/view/123",
        })

        # 期間の日付は「開始〜終了」、何も書かれていないページは記録なし
        ranged = {"type": "date", "date": {"start": "2024-05-03", "end": "2024-05-04"}}
        self.assertEqual(notion_sync.from_property(ranged), "2024-05-03〜2024-05-04")
        empty = notion_sync.page_values(_page("p2", "空", "2026-10-01T00:00:00.000Z",
                                              **{"GM": _text(""), "通過日": {"type": "date", "date": None}}),
                                        mapping, USER_SCHEMA)
        self.assertIn("play_log", empty)
        self.assertIsNone(empty["play_log"])


class TestApplyNotionPlayLog(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = Database(os.path.join(self.tmp, "pl.db"))
        self.item_id = self.db.save_item("C:/books/a.pdf", "影の館", "クトゥルフ神話TRPG", "2人", "3時間", "", "", None)

    def tearDown(self):
        self.db.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_03_updates_only_when_notion_changes(self):
        manual_id = self.db.add_play_log(self.item_id, session_date="2023-01-01", memo="手元で書いた記録")
        log = {"session_date": "2024-05-03", "gm": "Aさん", "character_name": "御手洗"}
        self.assertTrue(self.db.apply_notion_play_log(self.item_id, "page-1", log))
        self.assertFalse(self.db.apply_notion_play_log(self.item_id, "page-1", dict(log)), "同じ内容で書き換えている")

        logs = {l["id"]: l for l in self.db.get_play_logs(self.item_id)}
        self.assertEqual(len(logs), 2)
        imported = next(l for l in logs.values() if l["notion_page_id"] == "page-1")
        self.assertEqual((imported["gm"], imported["character_name"]), ("Aさん", "御手洗"))

        # 手元で直した内容は、Notion が変わっていなければそのまま
        self.db.update_play_log(imported["id"], session_date="2024-05-03", role="PL", character_name="御手洗",
                                result="生還", gm="Aさん")
        self.db.apply_notion_play_log(self.item_id, "page-1", dict(log))
        self.assertEqual(self._log(imported["id"])["result"], "生還")

        # Notion 側で変わったら、その内容で書き換える
        self.assertTrue(self.db.apply_notion_play_log(self.item_id, "page-1", dict(log, gm="Dさん")))
        self.assertEqual(self._log(imported["id"])["gm"], "Dさん")

        # Notion 側が空になったら取り込んだ記録だけを消す
        self.assertTrue(self.db.apply_notion_play_log(self.item_id, "page-1", None))
        self.assertEqual([l["id"] for l in self.db.get_play_logs(self.item_id)], [manual_id])

    def test_03b_update_without_gm_keeps_it(self):
        log_id = self.db.add_play_log(self.item_id, session_date="2024-01-01", gm="Aさん", sheet_url="https://x/1")
        self.db.update_play_log(log_id, session_date="2024-01-02", memo="追記")
        log = self._log(log_id)
        self.assertEqual((log["gm"], log["sheet_url"], log["memo"]), ("Aさん", "https://x/1", "追記"))

    def _log(self, log_id):
        return next(l for l in self.db.get_play_logs(self.item_id) if l["id"] == log_id)


class FakeUserNotion(base.FakeNotion):
    """利用者のデータベースと同じ列構成の偽 Notion"""

    def schema(self, ds):
        return dict(USER_SCHEMA)

    def put(self, page):
        self.pages[page["id"]] = page


class _UserSettings(base._FakeSettings):
    def get_json(self, section, key, default):
        return {}


class TestSyncImportsPlayLogs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        from gui_qt.dialogs import notion_sync_dialog as mod

        self.mod = mod
        self.tmp = tempfile.mkdtemp()
        self.db = Database(os.path.join(self.tmp, "sync.db"))
        self.fake = FakeUserNotion()
        self._orig = (mod.Settings, notion_sync.NotionClient, mod.app_settings.get_notion_import_limit)
        mod.Settings = _UserSettings
        notion_sync.NotionClient = lambda *a, **k: self.fake
        mod.app_settings.get_notion_import_limit = lambda: 0

    def tearDown(self):
        self.mod.Settings, notion_sync.NotionClient, self.mod.app_settings.get_notion_import_limit = self._orig
        self.db.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _sync(self):
        worker = self.mod.NotionSyncWorker(self.db)
        result = []
        worker.finished_all.connect(lambda s, f, e: result.append(e))
        worker.run()
        self.assertEqual(result[-1], "", result[-1])
        return worker

    def test_05_backfills_play_logs_of_already_synced_pages(self):
        edited = "2026-10-01T00:00:00.000Z"
        self.fake.put(_page("page-1", "影の館", edited,
                            **{"GM": _text("Aさん"), "PC名": _text("御手洗"),
                               "通過日": {"type": "date", "date": {"start": "2024-05-03"}}}))
        self.fake.put(_page("page-2", "未通過の本", edited))

        # 通過記録の取り込みに対応する前に同調済みだった状態（更新日時も、どこまで読んだかも記録済み）
        for pid, title in (("page-1", "影の館"), ("page-2", "未通過の本")):
            item_id = self.db.save_item(f"notion://{pid}", title, "", "", "", "", "", None)
            self.db.set_notion_link(item_id, pid)
            self.db.conn.execute("UPDATE items SET notion_last_edited_time = ? WHERE id = ?;", (edited, item_id))
        self.db.conn.commit()
        self.db.set_sync_state("notion_watermark:ds-1", edited)

        worker = self._sync()
        self.assertIsNone(self.fake.queries[-1], "初回は通過記録を読むため全ページを取得する")
        self.assertEqual(worker.imported_count, 0, "変わっていない本の内容まで取り込み直している")
        item_id = self.db.find_existing_item_for_notion(page_id="page-1")["id"]
        logs = self.db.get_play_logs(item_id)
        self.assertEqual(len(logs), 1)
        self.assertEqual((logs[0]["session_date"], logs[0]["gm"], logs[0]["character_name"]),
                         ("2024-05-03", "Aさん", "御手洗"))
        other_id = self.db.find_existing_item_for_notion(page_id="page-2")["id"]
        self.assertEqual(self.db.get_play_logs(other_id), [])

        # 2 回目以降は、更新されたページだけを取得する（記録が重複しない）
        self._sync()
        self.assertIsNotNone(self.fake.queries[-1])
        self.assertEqual(len(self.db.get_play_logs(item_id)), 1)

        # Notion 側で同卓者を書き足すと、次の同調で反映される
        page = self.fake.pages["page-1"]
        page["properties"]["同卓者（PC名）"] = _text("Bさん（佐藤）")
        page["last_edited_time"] = "2027-01-01T00:00:00.000Z"  # 同調で書き込まれた時刻より後
        self._sync()
        logs = self.db.get_play_logs(item_id)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["party_members"], "Bさん（佐藤）")
        self.assertEqual([c for c in self.fake.calls if c[0] == "create"], [], "取り込んだ本を Notion に作り直している")

    def test_05b_new_page_with_play_log(self):
        self.fake.put(_page("page-9", "新しい本", "2026-10-01T00:00:00.000Z",
                            **{"PC名": _text("鈴木"), "いあきゃら": {"type": "url", "url": "https://iachara.com/v/9"}}))
        self._sync()
        item_id = self.db.find_existing_item_for_notion(page_id="page-9")["id"]
        logs = self.db.get_play_logs(item_id)
        self.assertEqual([(l["character_name"], l["sheet_url"]) for l in logs], [("鈴木", "https://iachara.com/v/9")])


class TestPlayLogUi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_06_detail_shows_gm_and_sheet(self):
        import app_settings
        from gui_qt.dialogs.item_detail_dialog import ItemDetailDialog
        from gui_qt.dialogs.play_log_dialog import PlayLogEditDialog

        tmp = tempfile.mkdtemp()
        orig = (app_settings.SETTINGS_FILE, app_settings._settings_instance)
        app_settings.SETTINGS_FILE = os.path.join(tmp, "settings.ini")
        app_settings._settings_instance = None
        db = Database(os.path.join(tmp, "ui.db"))
        try:
            item_id = db.save_item("C:/books/a.pdf", "影の館", "クトゥルフ神話TRPG", "2人", "3時間", "", "", None)
            db.apply_notion_play_log(item_id, "page-1", {
                "gm": "Aさん", "party_members": "Bさん、Cさん", "sheet_url": "https://iachara.com/view/1",
            })
            dlg = ItemDetailDialog(item_id, db)
            dlg._render_play_logs()
            texts = " ".join(w.text() for w in dlg.findChildren(QLabel))
            self.assertIn("GM: Aさん", texts)
            self.assertIn("卓メンバー: Bさん、Cさん", texts)
            self.assertIn("https://iachara.com/view/1", texts)
            self.assertIn("Notion", texts)
            dlg.close()

            # 編集画面: 日付の無い記録は今日の日付で埋めず、GM・キャラシートを読み書きできる
            log = db.get_play_logs(item_id)[0]
            edit = PlayLogEditDialog(log_data=log)
            self.assertEqual(edit.date_edit.text(), "")
            self.assertEqual(edit.gm_edit.text(), "Aさん")
            edit.gm_edit.setText("Dさん")
            edit._on_save()
            self.assertEqual(edit.result_data["gm"], "Dさん")
            self.assertEqual(edit.result_data["sheet_url"], "https://iachara.com/view/1")
        finally:
            db.conn.close()
            app_settings.SETTINGS_FILE, app_settings._settings_instance = orig
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
