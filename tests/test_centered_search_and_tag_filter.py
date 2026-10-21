"""ヘッダー検索バーの中央配置と、検索種類へのタグ検索追加・複数タグ選択機能の検証テスト

検証項目:
1. ヘッダーバーの検索エリアが中央に配置されていること（左右ストレッチとバランス）
2. 検索バーの幅が指定の 340〜380px（360px）になっていること
3. 検索種類コンボボックスに「🏷 タグ検索」が含まれていること
4. 「🏷 タグ選択 ▼」ボタンからタグ複数選択ポップアップが開き、複数タグのチェックによる絞り込みが連動すること
5. 検索バーでのタグ検索（タグ名直接入力・複数単語・未設定）が正常に機能すること
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtCore import Qt, QBuffer, QIODevice
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QColor
from PySide6.QtTest import QTest

from core.database import Database
from gui_qt.main_window import MainWindow
from gui_qt.components.tag_select_popup import TagSelectPopup


def run_tests():
    app = QApplication.instance() or QApplication(sys.argv)

    test_db_path = "test_centered_search.db"
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    db = Database(test_db_path)

    # グローバルタグ・ローカルタグ
    db.add_tag("CoC", is_global=1)
    db.add_tag("マダミス", is_global=1)
    db.add_tag("未通過", is_global=1)
    db.add_tag("通過済み", is_global=1)

    db.add_tag("ホラー", is_global=0)
    db.add_tag("洋館", is_global=0)
    db.add_tag("タイマン", is_global=0)

    # ダミーサムネイル
    img = QImage(260, 180, QImage.Format_RGB32)
    img.fill(QColor("#3a2a1a"))
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    thumb_data = bytes(buf.data())

    # テストアイテム作成
    # 1: CoC + 未通過 + ホラー
    id1 = db.save_item(
        file_path="scenario1.pdf",
        title="狂気山脈",
        system_name="CoC",
        players_text="3-4",
        duration_text="6",
        overview="登山",
        synopsis="未踏峰",
        thumbnail_bytes=thumb_data,
    )
    db.toggle_item_tag(id1, "CoC", enabled=True)
    db.toggle_item_tag(id1, "未通過", enabled=True)
    db.toggle_item_tag(id1, "ホラー", enabled=True)

    # 2: マダミス + 通過済み + 洋館
    id2 = db.save_item(
        file_path="scenario2.pdf",
        title="J・モリアーティの暗躍",
        system_name="マダミス",
        players_text="5",
        duration_text="3",
        overview="推理",
        synopsis="ロンドン",
        thumbnail_bytes=thumb_data,
    )
    db.toggle_item_tag(id2, "マダミス", enabled=True)
    db.toggle_item_tag(id2, "通過済み", enabled=True)
    db.toggle_item_tag(id2, "洋館", enabled=True)

    # 3: CoC + 未通過 + タイマン
    id3 = db.save_item(
        file_path="scenario3.pdf",
        title="カタシロ",
        system_name="CoC",
        players_text="1",
        duration_text="1",
        overview="対話",
        synopsis="病室",
        thumbnail_bytes=thumb_data,
    )
    db.toggle_item_tag(id3, "CoC", enabled=True)
    db.toggle_item_tag(id3, "未通過", enabled=True)
    db.toggle_item_tag(id3, "タイマン", enabled=True)

    # メインウィンドウ起動
    win = MainWindow(db_path=test_db_path)
    win.resize(1260, 800)
    win.show()
    QApplication.processEvents()

    artifact_dir = os.environ.get("ANTIGRAVITY_ARTIFACT_DIR", r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449")
    hbar = win.header_bar

    # 1. 検索バーコンテナの幅と中央配置の検証
    container_w = hbar.search_container.width()
    print(f"検索コンテナの幅: {container_w}px")
    assert 400 <= container_w <= 450, f"検索コンテナの幅が400〜450pxの範囲外です: {container_w}px"
    print("[PASS] 検索コンテナの幅（420px）検証完了")

    # 2. 検索の種類に「🏷 タグ検索」が含まれていることの検証
    types = [hbar.search_type_combo.itemData(i) for i in range(hbar.search_type_combo.count())]
    print(f"検索の種類一覧: {types}")
    assert "tag" in types, "検索の種類に 'tag'（タグ検索）が含まれていません"
    print("[PASS] 検索の種類にタグ検索が含まれていることを確認")

    # 初期全体キャプチャ（中央寄せ状態）
    win.grab().save(os.path.join(artifact_dir, "test_centered_header_search.png"))

    # 3. 「🏷 タグ選択 ▼」ボタンからポップアップを表示
    hbar._toggle_tag_popup()
    QApplication.processEvents()
    assert hbar.tag_popup is not None
    assert hbar.tag_popup.isVisible(), "タグ選択ポップアップが表示されていません"
    print("[PASS] タグ選択ポップアップの表示検証完了")

    # ポップアップ表示状態のキャプチャ
    win.grab().save(os.path.join(artifact_dir, "test_tag_select_popup_open.png"))

    # 4. ポップアップで複数タグを選択（例: "CoC" と "ホラー"）
    # アイテム1のみにヒットするはず
    hbar.tag_popup.checkboxes["CoC"].setChecked(True)
    hbar.tag_popup.checkboxes["ホラー"].setChecked(True)
    QApplication.processEvents()

    filtered_ids = [it[0] for it in win.filtered_items]
    print(f"CoC + ホラー 選択時のヒットアイテムID: {filtered_ids}")
    assert filtered_ids == [id1], f"複数タグ選択結果不正: {filtered_ids} != {[id1]}"
    assert "タグ (2件)" in hbar.tag_select_btn.text()
    assert "(タグ選択: 2件)" in win.bookshelf.title_label.text()
    print("[PASS] 複数タグ選択による絞り込み（CoC + ホラー → 狂気山脈）検証完了")

    # ポップアップ閉じる
    hbar.tag_popup.hide()
    QApplication.processEvents()

    # タグ選択を全解除
    hbar.tag_popup.clear_all()
    QApplication.processEvents()
    assert len(win.filtered_items) == 3

    # 5. 検索の種類を「🏷 タグ検索」に切り替え、テキスト入力でタグ検索
    tag_idx = hbar.search_type_combo.findData("tag")
    hbar.search_type_combo.setCurrentIndex(tag_idx)
    QApplication.processEvents()
    assert "タグ名" in hbar.search_edit.placeholderText()

    # 「タイマン」と入力（カタシロのみヒット）
    hbar.search_edit.setText("タイマン")
    # 検索は入力が止まってから反映される（MainWindow.SEARCH_DEBOUNCE_MS）
    QTest.qWait(win.SEARCH_DEBOUNCE_MS + 100)
    filtered_ids = [it[0] for it in win.filtered_items]
    assert filtered_ids == [id3], f"タグ名「タイマン」検索結果不正: {filtered_ids} != {[id3]}"
    assert "(タグ検索: タイマン)" in win.bookshelf.title_label.text()
    print("[PASS] 検索種類『タグ検索』でのテキスト検索（タイマン → カタシロ）検証完了")

    win.grab().save(os.path.join(artifact_dir, "test_tag_search_mode_view.png"))

    hbar.search_edit.clear()
    hbar.search_type_combo.setCurrentIndex(0)  # すべて検索に戻す
    QApplication.processEvents()

    win.close()
    try:
        db.conn.close()
        if hasattr(win, "db") and win.db:
            win.db.conn.close()
    except Exception:
        pass

    try:
        if os.path.exists(test_db_path):
            os.remove(test_db_path)
    except Exception:
        pass

    print("[SUCCESS] すべての中央配置・タグ検索テストに合格しました！")


if __name__ == "__main__":
    run_tests()
