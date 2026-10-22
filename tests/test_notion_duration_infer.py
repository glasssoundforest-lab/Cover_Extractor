"""概要に書かれた所要時間・プレイ時間を、Notion から取り込んだ本の所要時間に反映する検証テスト"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import notion_sync
from core.database import Database
from core.web_extractor import WebScenarioExtractor as W

CASES = {
    "プレイ時間：2時間": "2時間",
    "推定時間…５時間～（テキセ）": "5時間～",
    "推定時間：1話2～3H/全体6～9H": "6～9時間",
    "プレイ時間…オンラインボイスセッションで8時間程度/テキストセッションで16時間程度": "8時間",
    "プレイ時間 キャンペーン方式、合計10時間（最低）": "10時間",
    "プレイ時間は90分程度を想定しています。（自由RPで変動あり）": "90分",
    "所要時間：ボイセ　16時間∼": "16時間～",
    "・時間：7 時間程度": "7 時間",
    "時間：1〜2h": "1〜2時間",
    "【所要時間】　ボイセ 約6〜8時間": "6〜8時間",
    "プレイ時間：2.5時間": "2.5時間",
    "時間だけが過ぎ、汗が流れた。": "",
}


class TestDurationInfer(unittest.TestCase):
    def test_extract(self):
        for text, want in CASES.items():
            self.assertEqual(W._extract_duration(text), want, text)

    def test_page_values_and_keep_local(self):
        schema = {"Name": "title", "概要": "rich_text"}
        page = {"id": "p", "properties": {
            "Name": {"type": "title", "title": [{"plain_text": "題"}]},
            "概要": {"type": "rich_text", "rich_text": [{"plain_text": "プレイ時間：2.5時間\n本文"}]},
        }}
        v = notion_sync.page_values(page, {"title": "Name", "overview": "概要"}, schema)
        self.assertEqual(v["duration_text"], "2.5時間")
        self.assertTrue(v["duration_inferred"])
        self.assertEqual(notion_sync.keep_local_duration(dict(v), "4時間")["duration_text"], "4時間")

    def test_db_import_and_backfill(self):
        tmp = tempfile.mkdtemp()
        try:
            path = os.path.join(tmp, "d.db")
            db = Database(path)
            vals = {"title": "題", "overview": "プレイ時間：3時間", "duration_text": "3時間", "duration_inferred": True}
            item_id = db.save_or_update_from_notion("p1", vals, None, last_edited_time="2026-01-01T00:00:00.000Z")
            self.assertEqual(db.get_item_detail_dict(item_id)["duration_text"], "3時間")
            db.update_item_meta(item_id, "題", "", "", "5時間")
            db.save_or_update_from_notion("p1", vals, None, last_edited_time="2026-01-02T00:00:00.000Z")
            self.assertEqual(db.get_item_detail_dict(item_id)["duration_text"], "5時間")

            # 取り込み済みで時間が空の本は、起動時に一度だけ概要から補う
            db.update_item_meta(item_id, "題", "", "", "")
            db.set_sync_state("notion_duration_infer_v1", None)
            db.conn.close()
            db = Database(path)
            self.assertEqual(db.get_item_detail_dict(item_id)["duration_text"], "3時間")
            db.conn.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
