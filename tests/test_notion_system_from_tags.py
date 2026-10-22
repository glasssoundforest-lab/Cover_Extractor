"""Notion から取り込んだシナリオのシステムを、Notion のタグから決める機能の検証テスト
(tests/test_notion_system_from_tags.py)

実際の Notion には接続しない。

1. タグ（CoC・マダミス・エモクロア・ストプレ等）からシステム名を決めること（決められなければ空のまま）
2. Notion にシステムの列が無いページを取り込むと、タグからシステムが入ること
3. 手元でシステムが入っている本は、タグから決めたシステムで書き換えず、食い違いとしても扱わないこと
4. 以前に取り込んでシステムが空のままの本には、一度だけタグからシステムを補うこと
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import notion_sync
from core.database import Database
from core.web_extractor import WebScenarioExtractor
import test_notion_background_sync as base
from test_notion_play_log_import import USER_SCHEMA, _page


def _tags(*names):
    return {"type": "multi_select", "multi_select": [{"name": n} for n in names]}


class TestSystemFromTags(unittest.TestCase):
    def test_01_guess_from_tags(self):
        guess = WebScenarioExtractor.guess_system_from_tags
        self.assertEqual(guess(["CoC", "未通過", "1PL"]), "クトゥルフ神話TRPG")
        self.assertEqual(guess(["新CoC"]), "新クトゥルフ神話TRPG")
        self.assertEqual(guess(["マダミス", "6PL"]), "マーダーミステリー")
        self.assertEqual(guess(["ストーリープレイング"]), "ストーリープレイング")
        self.assertEqual(guess(["ストプレ"]), "ストーリープレイング")
        self.assertEqual(guess(["エモクロア", "2PL"]), "エモクロアTRPG")
        self.assertEqual(guess(["ｃｏｃ"]), "クトゥルフ神話TRPG", "全角でも判定する")
        self.assertEqual(guess(["GM可", "5PL以上", "通過済み", "その他", "TRPM"]), "")
        self.assertEqual(guess([]), "")

    def test_02_page_values_without_system_column(self):
        mapping = notion_sync.guess_mapping(USER_SCHEMA)
        self.assertNotIn("system_name", mapping, "利用者の Notion にはシステムの列が無い")
        vals = notion_sync.page_values(
            _page("p1", "影の館", "2026-10-01T00:00:00.000Z", TAGs=_tags("CoC", "未通過", "1PL")), mapping, USER_SCHEMA)
        self.assertEqual(vals["system_name"], "クトゥルフ神話TRPG")
        self.assertTrue(vals["system_from_tags"])

        vals = notion_sync.page_values(
            _page("p2", "人数だけ", "2026-10-01T00:00:00.000Z", TAGs=_tags("5PL以上")), mapping, USER_SCHEMA)
        self.assertFalse(vals.get("system_name"))

        # システムの列があって値が入っていれば、そちらを使う
        schema = dict(USER_SCHEMA, システム="select")
        mapping = notion_sync.guess_mapping(schema)
        page = _page("p3", "影の館", "2026-10-01T00:00:00.000Z", TAGs=_tags("CoC"),
                     システム={"type": "select", "select": {"name": "新クトゥルフ神話TRPG"}})
        vals = notion_sync.page_values(page, mapping, schema)
        self.assertEqual(vals["system_name"], "新クトゥルフ神話TRPG")
        self.assertNotIn("system_from_tags", vals)


class TestSystemFromTagsInDb(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "sys.db")
        self.db = Database(self.path)

    def tearDown(self):
        self.db.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _system(self, item_id):
        return self.db.conn.execute("SELECT system_name FROM items WHERE id = ?;", (item_id,)).fetchone()[0]

    def test_03_import_fills_only_empty_system(self):
        derived = {"title": "影の館", "tags": ["CoC"], "system_name": "クトゥルフ神話TRPG", "system_from_tags": True}
        new_id = self.db.save_or_update_from_notion("page-1", dict(derived))
        self.assertEqual(self._system(new_id), "クトゥルフ神話TRPG")

        # 手元で新クトゥルフにしていたら、タグから決めた値で戻さない
        self.db.update_item_meta(new_id, "影の館", "新クトゥルフ神話TRPG", "", "")
        self.db.save_or_update_from_notion("page-1", dict(derived))
        self.assertEqual(self._system(new_id), "新クトゥルフ神話TRPG")

        # Notion のシステムの列に書かれた値なら、これまでどおり取り込む
        self.db.save_or_update_from_notion("page-1", {"title": "影の館", "system_name": "エモクロアTRPG"})
        self.assertEqual(self._system(new_id), "エモクロアTRPG")

        vals = {"system_name": "クトゥルフ神話TRPG", "system_from_tags": True}
        self.assertEqual(notion_sync.keep_local_system(dict(vals), "新クトゥルフ神話TRPG")["system_name"],
                         "新クトゥルフ神話TRPG")
        self.assertEqual(notion_sync.keep_local_system(dict(vals), "")["system_name"], "クトゥルフ神話TRPG")

    def test_04_backfill_once_for_notion_items(self):
        notion_id = self.db.save_item("notion://page-1", "影の館", "", "", "", "", "", None)
        self.db.add_tags_to_item(notion_id, ["CoC", "未通過"])
        linked_id = self.db.save_item("C:/books/linked.pdf", "マダミスの本", "", "", "", "", "", None)
        self.db.set_notion_link(linked_id, "page-2")
        self.db.add_tags_to_item(linked_id, ["マダミス"])
        kept_id = self.db.save_item("notion://page-3", "新版", "新クトゥルフ神話TRPG", "", "", "", "", None)
        self.db.add_tags_to_item(kept_id, ["CoC"])
        local_id = self.db.save_item("C:/books/local.pdf", "手元の本", "", "", "", "", "", None)
        self.db.add_tags_to_item(local_id, ["CoC"])
        self.db.set_sync_state("notion_system_from_tags_v1", None)  # まだ補っていない状態にする
        self.db.conn.close()

        self.db = Database(self.path)
        self.assertEqual(self._system(notion_id), "クトゥルフ神話TRPG")
        self.assertEqual(self._system(linked_id), "マーダーミステリー")
        self.assertEqual(self._system(kept_id), "新クトゥルフ神話TRPG", "手元で決めたシステムを書き換えた")
        self.assertIn(self._system(local_id), (None, ""), "Notion と関係ない本まで書き換えた")

        # 補うのは一度だけ（利用者が後で空にしたシステムを、開くたびに入れ直さない）
        self.db.update_item_meta(notion_id, "影の館", "", "", "")
        self.db.conn.close()
        self.db = Database(self.path)
        self.assertIn(self._system(notion_id), (None, ""))


class FakeUserNotion(base.FakeNotion):
    def schema(self, ds):
        return dict(USER_SCHEMA)


class _UserSettings(base._FakeSettings):
    def get_json(self, section, key, default):
        return {}


class TestSyncWithTagSystem(unittest.TestCase):
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

    def _sync(self, auto=False):
        worker = self.mod.NotionSyncWorker(self.db)
        worker.defer_conflicts = auto
        result = []
        worker.finished_all.connect(lambda s, f, e: result.append(e))
        worker.run()
        self.assertEqual(result[-1], "", result[-1])
        return worker

    def test_05_sync_sets_system_and_respects_local(self):
        self.fake.pages["page-1"] = _page("page-1", "影の館", "2026-10-01T00:00:00.000Z", TAGs=_tags("CoC", "未通過"))
        self._sync()
        item = self.db.find_existing_item_for_notion(page_id="page-1")
        self.assertEqual(item["system_name"], "クトゥルフ神話TRPG")

        # 手元で新クトゥルフに直した後に Notion 側でページが更新されても、食い違いとして保留せず手元の値を保つ
        self.db.update_item_meta(item["id"], "影の館", "新クトゥルフ神話TRPG", "", "")
        page = self.fake.pages["page-1"]
        page["last_edited_time"] = "2027-01-01T00:00:00.000Z"
        worker = self._sync(auto=True)
        self.assertEqual(worker.deferred_count, 0, "タグから決めたシステムを食い違いとして扱った")
        self.assertEqual(self.db.find_existing_item_for_notion(page_id="page-1")["system_name"], "新クトゥルフ神話TRPG")


if __name__ == "__main__":
    unittest.main()
