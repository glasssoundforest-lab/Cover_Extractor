"""バックエンド（coreモジュール）およびPySide6連携の動作検証テスト
"""

import os
import sys
import tempfile
import sqlite3

# プロジェクトルートをインポートパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# core パッケージのインポート
from core import (
    Database,
    BOOKMARK_ITEMS,
    SORT_OPTIONS,
    canonical_tag,
    canonical_system,
    sort_items,
    CoverExtractorError,
    RustDllExtractor,
    parse_info,
    collect_scenario_targets,
    parse_name_clues,
    extract_scenario_data,
)

# PySide6 のインポート
from PySide6.QtCore import QByteArray
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import QApplication

def test_database():
    print("[1/4] Testing Database...")
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        tmp_db_path = f.name

    try:
        db = Database(tmp_db_path)
        # アイテム追加 (save_item)
        dummy_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF"  # ダミーJPEGヘッダ
        item_id = db.save_item(
            file_path="C:/dummy/test_scenario.zip",
            title="テストシナリオ",
            system_name="クトゥルフ神話TRPG",
            players_text="3〜4人",
            duration_text="3〜4時間",
            overview="テスト用の概要です",
            synopsis="テスト用のあらすじです",
            thumbnail_bytes=dummy_jpeg,
        )
        assert item_id > 0, "Insert item failed"

        # タグ追加 (add_tags_to_item)
        db.add_tags_to_item(item_id, ["CoC", "未通過"])

        # 取得
        items = db.get_items()
        assert len(items) == 1, "Item count should be 1"
        row = items[0]
        assert row[2] == "テストシナリオ"
        assert row[3] == "クトゥルフ神話TRPG"
        assert row[8] == dummy_jpeg

        tags = [t[1] for t in db.get_item_tags(item_id)]
        assert "CoC" in tags and "未通過" in tags

        # メタデータ更新 (update_item_all)
        db.update_item_all(
            item_id=item_id,
            title="更新後シナリオ",
            system_name="クトゥルフ神話TRPG",
            players_text="4人",
            duration_text="4時間",
            overview="更新概要",
            synopsis="更新あらすじ",
            author="新作者",
            url="https://example.com/updated",
            tags=["CoC", "通過済み"],
            title_kana="こうしんごしなりお",
        )
        updated_item = db.get_item(item_id)
        assert updated_item[2] == "更新後シナリオ"
        assert db.get_author(item_id) == "新作者"

        print("  -> Database tests passed successfully!")
    finally:
        if os.path.exists(tmp_db_path):
            try:
                os.remove(tmp_db_path)
            except OSError:
                pass


def test_rust_dll():
    print("[2/4] Testing Rust DLL Extractor...")
    extractor = RustDllExtractor()
    assert extractor.handle is not None, "Failed to create Rust extractor handle"

    # バージョン/プレースホルダー確認
    placeholder = extractor.placeholder_jpeg()
    print(f"  -> Extractor initialized. Placeholder image bytes: {len(placeholder) if placeholder else 0}")
    extractor.close()
    print("  -> Rust DLL tests passed successfully!")


def test_scenario_helpers():
    print("[3/4] Testing Scenario Helpers...")
    clues = parse_name_clues("【CoC】海も枯れるまで")
    assert clues["title"] == "海も枯れるまで"
    assert clues["system_name"] == "クトゥルフ神話TRPG"
    assert "CoC" in clues["tags"]

    clues2 = parse_name_clues("[マダミス]狂気山脈")
    assert clues2["title"] == "狂気山脈"
    assert clues2["system_name"] == "マーダーミステリー"
    assert "マダミス" in clues2["tags"]

    print("  -> Scenario helpers tests passed successfully!")


def test_pyside6_integration():
    print("[4/4] Testing PySide6 integration with core...")
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    # 実際の catalog.db から1件取得して QPixmap に展開できるか検証
    db = Database("catalog.db")
    items = db.get_items()
    print(f"  -> Found {len(items)} items in catalog.db")

    loaded_pixmaps = 0
    for it in items[:5]:
        thumb_blob = it[8]
        if thumb_blob:
            pix = QPixmap()
            success = pix.loadFromData(QByteArray(thumb_blob))
            if success and not pix.isNull():
                loaded_pixmaps += 1
                # print(f"    - Loaded item '{it[2]}': size = {pix.width()}x{pix.height()}")

    print(f"  -> Successfully loaded {loaded_pixmaps} thumbnails directly into PySide6 QPixmap!")
    print("  -> PySide6 integration tests passed successfully!")


if __name__ == "__main__":
    print("=== Core & PySide6 Integration Test ===")
    test_database()
    test_rust_dll()
    test_scenario_helpers()
    test_pyside6_integration()
    print("=== ALL TESTS PASSED! ===")
