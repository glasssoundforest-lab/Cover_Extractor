"""Notion から取り込んだ本の人数を、概要の文章・人数タグから決める検証テスト (tests/test_notion_players_infer.py)"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import notion_sync
from core.database import Database
from core.web_extractor import WebScenarioExtractor

SCHEMA = {"Name": "title", "概要": "rich_text", "タグ": "multi_select", "人数": "rich_text"}
MAPPING = {"title": "Name", "overview": "概要", "tags": "タグ"}


def page(overview="", tags=(), players=None):
    props = {
        "Name": {"type": "title", "title": [{"plain_text": "テスト"}]},
        "概要": {"type": "rich_text", "rich_text": [{"plain_text": overview}] if overview else []},
        "タグ": {"type": "multi_select", "multi_select": [{"name": t} for t in tags]},
    }
    mapping = dict(MAPPING)
    if players is not None:
        props["人数"] = {"type": "rich_text", "rich_text": [{"plain_text": players}] if players else []}
        mapping["players_text"] = "人数"
    return {"id": "p1", "properties": props}, mapping


class TestPlayersInfer(unittest.TestCase):
    def test_tags(self):
        g = WebScenarioExtractor.guess_players_from_tags
        self.assertEqual(g(["CoC", "4PL"]), "4人")
        self.assertEqual(g(["2〜4PL"]), "2〜4人")
        self.assertEqual(g(["5PL以上"]), "5人以上")
        self.assertEqual(g(["３人"]), "3人")
        self.assertEqual(g(["タイマン"]), "1人")
        self.assertEqual(g(["CoC", "2時間", "ホラー"]), "")

    def test_from_overview(self):
        p, m = page(overview="■人数：2〜4人\n■時間：3時間\n洋館で事件が起きる")
        self.assertEqual(notion_sync.page_values(p, m, SCHEMA)["players_text"], "2〜4人")

    def test_from_tag(self):
        p, m = page(overview="洋館で事件が起きる", tags=["CoC", "3PL"])
        v = notion_sync.page_values(p, m, SCHEMA)
        self.assertEqual(v["players_text"], "3人")
        self.assertTrue(v["players_inferred"])

    def test_explicit_column_wins(self):
        p, m = page(overview="人数：2人", tags=["3PL"], players="1人")
        v = notion_sync.page_values(p, m, SCHEMA)
        self.assertEqual(v["players_text"], "1人")
        self.assertNotIn("players_inferred", v)

    def test_keep_local(self):
        v = {"players_text": "3人", "players_inferred": True}
        self.assertEqual(notion_sync.keep_local_players(v, "5人")["players_text"], "5人")
        v = {"players_text": "3人", "players_inferred": True}
        self.assertEqual(notion_sync.keep_local_players(v, "")["players_text"], "3人")

    def test_db_import_and_backfill(self):
        tmp = tempfile.mkdtemp()
        try:
            db = Database(os.path.join(tmp, "d.db"))
            p, m = page(overview="洋館", tags=["CoC", "3PL"])
            values = notion_sync.page_values(p, m, SCHEMA)
            item_id = db.save_or_update_from_notion("p1", values, None, last_edited_time="2026-01-01T00:00:00.000Z")
            self.assertEqual(db.get_item_detail_dict(item_id)["players_text"], "3人")

            # 手元で人数を決めていれば、次の取り込みで上書きしない
            db.update_item_meta(item_id, "テスト", "", "5人", "")
            db.save_or_update_from_notion("p1", values, None, last_edited_time="2026-01-02T00:00:00.000Z")
            self.assertEqual(db.get_item_detail_dict(item_id)["players_text"], "5人")

            # 取り込み済みで人数が空の本は、起動時に一度だけ補う
            db.update_item_meta(item_id, "テスト", "", "", "")
            db.set_sync_state("notion_players_infer_v1", None)
            db.conn.close()
            db = Database(os.path.join(tmp, "d.db"))
            self.assertEqual(db.get_item_detail_dict(item_id)["players_text"], "3人")
            db.conn.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
