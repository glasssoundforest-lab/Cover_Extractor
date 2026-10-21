"""NotionDiffDialog（書架対照録）のスクリーンショット撮影とUI表示検証
(tests/test_notion_diff_dialog_screenshot.py)
"""

import io
import os
import sys
import unittest
from unittest.mock import MagicMock, patch
from PIL import Image

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from core.database import Database
import notion_sync
from gui_qt.dialogs.notion_diff_dialog import NotionDiffDialog

ARTIFACT_DIR = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449"


def _make_dummy_image_bytes(color=(120, 40, 40), size=(120, 170)) -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", size, color=color)
    img.save(buf, format="JPEG")
    return buf.getvalue()


def run_screenshot_test():
    app = QApplication.instance() or QApplication(sys.argv)

    test_db_path = os.path.join(ROOT_DIR, "test_diff_screenshot.db")
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    db = Database(test_db_path)
    cover_1 = _make_dummy_image_bytes(color=(40, 100, 140))
    cover_2 = _make_dummy_image_bytes(color=(140, 80, 40))

    # 1. 手元のみのシナリオ
    id_local_1 = db.save_item(
        file_path="local://arcanum_tome.pdf",
        title="秘術の魔道書",
        system_name="クトゥルフ神話TRPG",
        players_text="3〜4人",
        duration_text="4時間",
        overview="古の書架に眠る禁断の魔道書をめぐる探索行。",
        synopsis="探索者たちは失われた写本を探して古い洋館へと向かう...",
        thumbnail_bytes=cover_1,
    )
    with db.conn:
        db.conn.execute("UPDATE items SET author = ? WHERE id = ?;", ("円環の魔術師", id_local_1))

    id_local_2 = db.save_item(
        file_path="local://alchemist_lab.pdf",
        title="錬金術師の残照",
        system_name="エモクロアTRPG",
        players_text="2人",
        duration_text="3時間",
        overview="夕暮れの工房に残された最後の調合録。",
        synopsis="共鳴者たちは調合台に残されたメモを手がかりに...",
        thumbnail_bytes=None,
    )

    # 2. 双方に存在するが項目が不足・差異あり
    id_partial = db.save_item(
        file_path="local://phantom_opera.pdf",
        title="幻影のオペラ座",
        system_name="マダミス",
        players_text="5人",
        duration_text=None,  # 手元には時間がない
        overview="仮面舞踏会の夜、舞台裏で発生した怪事件。",
        synopsis=None,
        thumbnail_bytes=cover_2,
    )
    db.set_notion_link(id_partial, "notion-pid-opera")
    with db.conn:
        db.conn.execute("UPDATE items SET author = ? WHERE id = ?;", ("ガストン", id_partial))

    # 3. 完全一致
    id_sync = db.save_item(
        file_path="local://clockwork_city.pdf",
        title="歯車の都",
        system_name="シノビガミ",
        players_text="4人",
        duration_text="3時間",
        overview="蒸気と歯車が支配する地下都市の忍びたち。",
        synopsis="忍びたちは密命を受け、大時計の心臓部へ潜入する...",
        thumbnail_bytes=None,
    )
    db.set_notion_link(id_sync, "notion-pid-clockwork")

    # 模擬 Notion ページ
    page_opera = {
        "id": "notion-pid-opera",
        "last_edited_time": "2026-10-18T08:00:00.000Z",
        "properties": {
            "シナリオ名": {"type": "title", "title": [{"plain_text": "幻影のオペラ座"}]},
            "システム": {"type": "select", "select": {"name": "マダミス"}},
            "作者": {"type": "rich_text", "rich_text": [{"plain_text": "ガストン"}]},
            "所要時間": {"type": "number", "number": 150},  # Notionには時間がある
            "PL人数": {"type": "number", "number": 5},
            "概要": {"type": "rich_text", "rich_text": []},  # Notion側は概要が空
        },
    }

    page_clockwork = {
        "id": "notion-pid-clockwork",
        "last_edited_time": "2026-10-18T08:00:00.000Z",
        "properties": {
            "シナリオ名": {"type": "title", "title": [{"plain_text": "歯車の都"}]},
            "システム": {"type": "select", "select": {"name": "シノビガミ"}},
            "PL人数": {"type": "number", "number": 4},
            "所要時間": {"type": "number", "number": 180},
            "概要": {"type": "rich_text", "rich_text": [{"plain_text": "蒸気と歯車が支配する地下都市の忍びたち。"}]},
        },
    }

    page_remote_1 = {
        "id": "notion-pid-star-express",
        "last_edited_time": "2026-10-18T08:00:00.000Z",
        "properties": {
            "シナリオ名": {"type": "title", "title": [{"plain_text": "銀河鉄道の夜宴"}]},
            "システム": {"type": "select", "select": {"name": "クトゥルフ神話TRPG"}},
            "作者": {"type": "rich_text", "rich_text": [{"plain_text": "宮沢車掌"}]},
            "PL人数": {"type": "number", "number": 3},
            "所要時間": {"type": "number", "number": 240},
            "概要": {"type": "rich_text", "rich_text": [{"plain_text": "星空を駆ける列車で繰り広げられる夜宴の秘密。"}]},
            "タグ": {"type": "multi_select", "multi_select": [{"name": "CoC"}, {"name": "宇宙"}]},
        },
    }

    schema = {
        "シナリオ名": "title",
        "システム": "select",
        "作者": "rich_text",
        "PL人数": "number",
        "所要時間": "number",
        "概要": "rich_text",
        "タグ": "multi_select",
    }
    mapping = {
        "title": "シナリオ名",
        "system_name": "システム",
        "author": "作者",
        "players_text": "PL人数",
        "duration_text": "所要時間",
        "overview": "概要",
        "tags": "タグ",
    }

    mock_client = MagicMock()
    mock_client.schema.return_value = schema
    mock_client.query_all.return_value = [page_opera, page_clockwork, page_remote_1]

    # audit_notion_diff の結果をダイアログに反映
    diff_result = notion_sync.audit_notion_diff(
        db,
        mock_client,
        "src_123",
        mapping=mapping,
        schema=schema,
    )
    diff_result["client"] = mock_client
    diff_result["data_source_id"] = "src_123"

    with patch.object(NotionDiffDialog, "_start_audit", lambda self: None):
        dlg = NotionDiffDialog(db)
        dlg._on_audit_finished(diff_result)
        dlg.show()
        app.processEvents()


    # 1. タブ0: 手元のみ
    dlg.tabs.setCurrentIndex(0)
    app.processEvents()
    out1 = os.path.join(ARTIFACT_DIR, "test_notion_diff_tab0_local_only.png")
    dlg.grab().save(out1)
    print(f"[OK] Saved {out1}")

    # 2. タブ1: Notionのみ
    dlg.tabs.setCurrentIndex(1)
    app.processEvents()
    out2 = os.path.join(ARTIFACT_DIR, "test_notion_diff_tab1_notion_only.png")
    dlg.grab().save(out2)
    print(f"[OK] Saved {out2}")

    # 3. タブ2: 項目不足・差異あり
    dlg.tabs.setCurrentIndex(2)
    app.processEvents()
    out3 = os.path.join(ARTIFACT_DIR, "test_notion_diff_tab2_field_lacking.png")
    dlg.grab().save(out3)
    print(f"[OK] Saved {out3}")

    dlg.close()


if __name__ == "__main__":
    run_screenshot_test()
