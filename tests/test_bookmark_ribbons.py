"""表紙右上のしおりリボン表示および詳細画面タグ枠クリーン化の自動テスト
(tests/test_bookmark_ribbons.py)
"""

import sys
import os
import shutil

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QTimer, Qt
from core.database import Database
from gui_qt.main_window import MainWindow
from gui_qt.dialogs.item_detail_dialog import ItemDetailDialog

QMessageBox.information = lambda *args, **kwargs: QMessageBox.Ok
QMessageBox.warning = lambda *args, **kwargs: QMessageBox.Ok
QMessageBox.question = lambda *args, **kwargs: QMessageBox.Yes

ARTIFACT_DIR = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449"


def run_test():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    test_db_path = os.path.join(ROOT_DIR, "test_ribbons.db")
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    db = Database(test_db_path)

    # 1. テストアイテムの作成
    # アイテム1: お気に入りON、グローバルタグ2つ（CoC:深緑, 未通過:青藍）、ローカルタグ1つ（登山隊）
    id1 = db.save_item(
        file_path="M:/Tool/Cover_extractor/scenario1.txt",
        title="狂気山脈 〜邪神の山嶺〜",
        system_name="クトゥルフ神話TRPG",
        players_text="3-4",
        duration_text="6-8",
        overview="極限の登山サバイバル。",
        synopsis="未踏峰の頂へ。",
        thumbnail_bytes=None,
    )
    db.set_favorite(id1, True)
    db.toggle_item_tag(id1, "CoC", enabled=True)
    db.toggle_item_tag(id1, "未通過", enabled=True)
    db.add_tag("登山隊", color="#795548", is_global=0)
    db.toggle_item_tag(id1, "登山隊", enabled=True)

    # アイテム2: グローバルタグ3つ（マダミス:深紫, 通過済み:深紅, GM可:真鍮金）
    id2 = db.save_item(
        file_path="M:/Tool/Cover_extractor/scenario2.txt",
        title="四人の令嬢と灰被りの館",
        system_name="マーダーミステリー",
        players_text="4",
        duration_text="3",
        overview="館で起きた華麗なる悲劇。",
        synopsis="真実を暴くのは誰か。",
        thumbnail_bytes=None,
    )
    db.toggle_item_tag(id2, "マダミス", enabled=True)
    db.toggle_item_tag(id2, "通過済み", enabled=True)
    db.toggle_item_tag(id2, "GM可", enabled=True)

    # アイテム3: タグなし
    id3 = db.save_item(
        file_path="M:/Tool/Cover_extractor/scenario3.txt",
        title="名もなき古書の断片",
        system_name="エモクロアTRPG",
        players_text="1",
        duration_text="2",
        overview="断片的な記録。",
        synopsis="古書の頁がめくられる。",
        thumbnail_bytes=None,
    )

    refs = {}

    # -------------------------------------------------------------
    # ステップ1: 詳細画面のタグ枠キャプチャ（区分プレフィックスなし）
    # -------------------------------------------------------------
    def step1_capture_detail_clean():
        detail = ItemDetailDialog(id1, db=db, item_ids=[id1, id2, id3])
        refs["detail"] = detail
        detail.show()
        app.processEvents()

        # タグ枠テキストの検証
        tag_text = detail.tags_box.text()
        print(f"[OK] Detail tags_box text: {tag_text}")
        assert "グローバル" not in tag_text, "タグ枠に「グローバル」が含まれてしまっています"
        assert "ローカル" not in tag_text, "タグ枠に「ローカル」が含まれてしまっています"
        assert "CoC" in tag_text
        assert "未通過" in tag_text
        assert "登山隊" in tag_text

        pix = detail.grab()
        pix.save(os.path.join(ARTIFACT_DIR, "item_detail_clean_tags.png"))
        print("[OK] item_detail_clean_tags.png saved")

        detail.close()
        QTimer.singleShot(400, step2_capture_main_window_grid)

    # -------------------------------------------------------------
    # ステップ2: メインウィンドウ（グリッド表示）での表紙右上しおりキャプチャ
    # -------------------------------------------------------------
    def step2_capture_main_window_grid():
        mw = MainWindow(db_path=test_db_path)
        refs["mw"] = mw
        mw.show()
        app.processEvents()

        # 書架のカード数としおりの検証
        cards = mw.bookshelf.cards
        assert len(cards) == 3, f"Expected 3 cards, got {len(cards)}"

        # アイテム1のカード検証（しおり2枚: CoC, 未通過）
        card1 = next(c for c in cards if c.item_id == id1)
        assert len(card1.bookmark_ribbons) == 2, f"Expected 2 ribbons for item1, got {len(card1.bookmark_ribbons)}"
        assert card1.fav_badge.isVisible(), "お気に入りバッジが表示されていません"

        # アイテム2のカード検証（しおり3枚: マダミス, 通過済, GM可）
        card2 = next(c for c in cards if c.item_id == id2)
        assert len(card2.bookmark_ribbons) == 3, f"Expected 3 ribbons for item2, got {len(card2.bookmark_ribbons)}"

        # アイテム3のカード検証（しおり0枚）
        card3 = next(c for c in cards if c.item_id == id3)
        assert len(card3.bookmark_ribbons) == 0, f"Expected 0 ribbons for item3, got {len(card3.bookmark_ribbons)}"

        pix = mw.grab()
        pix.save(os.path.join(ARTIFACT_DIR, "bookshelf_bookmark_ribbons_grid.png"))
        print("[OK] bookshelf_bookmark_ribbons_grid.png saved")

        QTimer.singleShot(400, step3_capture_main_window_list)

    # -------------------------------------------------------------
    # ステップ3: メインウィンドウ（リスト表示）での表紙右上しおりキャプチャ
    # -------------------------------------------------------------
    def step3_capture_main_window_list():
        mw = refs["mw"]
        mw.bookshelf.set_view_mode("list")
        app.processEvents()

        list_cards = mw.bookshelf.cards
        card1 = next(c for c in list_cards if c.item_id == id1)
        assert len(card1.bookmark_ribbons) == 2, f"Expected 2 ribbons for item1 in list, got {len(card1.bookmark_ribbons)}"

        pix = mw.grab()
        pix.save(os.path.join(ARTIFACT_DIR, "bookshelf_bookmark_ribbons_list.png"))
        print("[OK] bookshelf_bookmark_ribbons_list.png saved")

        QTimer.singleShot(400, step4_toggle_tag_and_verify)

    # -------------------------------------------------------------
    # ステップ4: 右クリックメニュー等でタグ追加・解除したときの動的反映
    # -------------------------------------------------------------
    def step4_toggle_tag_and_verify():
        mw = refs["mw"]
        # アイテム1に「GM可」を追加
        db.toggle_item_tag(id1, "GM可", enabled=True)
        mw.reload_data()
        app.processEvents()

        # 再びグリッドに戻す
        mw.bookshelf.set_view_mode("medium")
        app.processEvents()

        card1 = next(c for c in mw.bookshelf.cards if c.item_id == id1)
        assert len(card1.bookmark_ribbons) == 3, f"Expected 3 ribbons after toggle, got {len(card1.bookmark_ribbons)}"

        pix = mw.grab()
        pix.save(os.path.join(ARTIFACT_DIR, "bookshelf_bookmark_ribbons_updated.png"))
        print("[OK] bookshelf_bookmark_ribbons_updated.png saved")

        mw.close()

        # クリーンアップ
        try:
            if os.path.exists(test_db_path):
                os.remove(test_db_path)
        except Exception:
            pass

        print("[ALL RIBBON TESTS PASSED SUCCESSFULLY]")
        app.quit()

    QTimer.singleShot(500, step1_capture_detail_clean)
    app.exec()


if __name__ == "__main__":
    run_test()
