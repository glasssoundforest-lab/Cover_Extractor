"""グローバルタグ「未設定」絞り込み、およびローカルタグ検索での「未設定/タグなし」絞り込みの検証テスト

検証項目:
1. サイドバーのタグセクションに「未設定」ピルボタンが存在し、2列均等に配置されていること
2. サイドバーに「🔍 ローカルタグ検索」入力欄が新設されていること
3. グローバルタグ「未設定」ボタンを選択すると、グローバルタグが付いていないシナリオのみが絞り込まれること
4. グローバルタグ「未設定」と通常のグローバルタグが排他的にトグルされること
5. サイドバーのローカルタグ検索欄に「未設定」「タグなし」を入力すると、ローカルタグが付いていないシナリオのみが絞り込まれること
6. 上部ヘッダーの検索バーに「タグなし」を入力すると、ローカルタグが付いていないシナリオが絞り込まれること
7. グローバルタグ未設定 ＋ ローカルタグ未設定 のAND絞り込みが正確に機能すること
"""

import os
import sys

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtCore import Qt, QBuffer, QIODevice
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QColor
from PySide6.QtTest import QTest

from core.database import Database
from gui_qt.main_window import MainWindow
from gui_qt.components.ornate import PillTag


def run_tests():
    app = QApplication.instance() or QApplication(sys.argv)

    test_db_path = "test_unset_tags.db"
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    db = Database(test_db_path)

    # グローバルタグとローカルタグの登録
    db.add_tag("CoC", is_global=1)
    db.add_tag("マダミス", is_global=1)
    db.add_tag("未通過", is_global=1)
    db.add_tag("通過済み", is_global=1)
    db.add_tag("GM可", is_global=1)

    db.add_tag("ホラー", is_global=0)
    db.add_tag("洋館", is_global=0)
    db.add_tag("タイマン", is_global=0)

    # ダミー画像
    img = QImage(260, 180, QImage.Format_RGB32)
    img.fill(QColor("#3a2a1a"))
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    thumb_data = bytes(buf.data())

    # 4パターンのテストデータ作成
    # アイテム1: グローバルタグあり (CoC, 未通過), ローカルタグあり (ホラー)
    id1 = db.save_item(
        file_path="scenario1.pdf",
        title="1. 狂気山脈 (Gあり・Lあり)",
        system_name="CoC",
        players_text="3-4",
        duration_text="6",
        overview="登山",
        synopsis="頂へ",
        thumbnail_bytes=thumb_data,
    )
    db.toggle_item_tag(id1, "CoC", enabled=True)
    db.toggle_item_tag(id1, "未通過", enabled=True)
    db.toggle_item_tag(id1, "ホラー", enabled=True)

    # アイテム2: グローバルタグあり (マダミス), ローカルタグなし (0件)
    id2 = db.save_item(
        file_path="scenario2.pdf",
        title="2. J・モリアーティ (Gあり・Lなし)",
        system_name="マダミス",
        players_text="5",
        duration_text="3",
        overview="推理",
        synopsis="霧の街",
        thumbnail_bytes=thumb_data,
    )
    db.toggle_item_tag(id2, "マダミス", enabled=True)

    # アイテム3: グローバルタグなし (0件), ローカルタグあり (タイマン)
    id3 = db.save_item(
        file_path="scenario3.pdf",
        title="3. カタシロ (Gなし・Lあり)",
        system_name="CoC",
        players_text="1",
        duration_text="1",
        overview="対話",
        synopsis="病室",
        thumbnail_bytes=thumb_data,
    )
    db.toggle_item_tag(id3, "タイマン", enabled=True)

    # アイテム4: グローバルタグなし (0件), ローカルタグなし (0件)
    id4 = db.save_item(
        file_path="scenario4.pdf",
        title="4. 白紙の古文書 (Gなし・Lなし)",
        system_name="その他",
        players_text="1",
        duration_text="1",
        overview="白紙",
        synopsis="記録なし",
        thumbnail_bytes=thumb_data,
    )

    # メインウィンドウ起動
    win = MainWindow(db_path=test_db_path)
    win.resize(1150, 750)
    win.show()
    QApplication.processEvents()

    artifact_dir = os.environ.get("ANTIGRAVITY_ARTIFACT_DIR", r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449")
    sidebar = win.sidebar

    # 1. サイドバーUIの検証
    assert "未設定" in sidebar.tag_widgets, "サイドバーのタグ一覧に「未設定」ピルボタンが存在しません"
    assert hasattr(sidebar, "local_tag_search_edit"), "サイドバーにローカルタグ検索入力欄が存在しません"
    print("[PASS] サイドバーの「未設定」ピルボタンおよびローカルタグ検索欄の存在確認完了")

    # 2. グローバルタグ「未設定」の絞り込み検証（アイテム3, 4のみヒット）
    unset_pill = sidebar.tag_widgets["未設定"]
    QTest.mouseClick(unset_pill, Qt.LeftButton)
    QApplication.processEvents()

    filtered_ids = [it[0] for it in win.filtered_items]
    print(f"グローバルタグ「未設定」選択時のアイテムID: {filtered_ids}")
    assert set(filtered_ids) == {id3, id4}, f"グローバルタグ未設定の絞り込み結果不正: {filtered_ids} != {[id3, id4]}"
    assert "(タグ未設定)" in win.bookshelf.title_label.text()
    print("[PASS] グローバルタグ「未設定」による絞り込み検証完了（アイテム3, 4の2件）")

    win.grab().save(os.path.join(artifact_dir, "test_global_tag_unset_view.png"))

    # 3. 排他トグル動作の検証
    coc_pill = sidebar.tag_widgets["CoC"]
    QTest.mouseClick(coc_pill, Qt.LeftButton)
    QApplication.processEvents()

    assert not unset_pill.is_checked, "CoCを選択したときに未設定が解除されていません"
    assert coc_pill.is_checked, "CoCが選択されていません"
    filtered_ids = [it[0] for it in win.filtered_items]
    assert id1 in filtered_ids and id4 not in filtered_ids
    print("[PASS] 「未設定」と通常タグ（CoC）の排他トグル検証完了")

    # CoCを解除して全件に戻す
    QTest.mouseClick(coc_pill, Qt.LeftButton)
    QApplication.processEvents()
    assert len(win.filtered_items) == 4

    # 4. サイドバーのローカルタグ検索欄で「未設定」入力の検証（アイテム2, 4のみヒット）
    sidebar.local_tag_search_edit.setText("未設定")
    QApplication.processEvents()
    filtered_ids = [it[0] for it in win.filtered_items]
    print(f"サイドバーローカルタグ「未設定」検索時のアイテムID: {filtered_ids}")
    assert set(filtered_ids) == {id2, id4}, f"ローカルタグ未設定の絞り込み結果不正: {filtered_ids} != {[id2, id4]}"
    assert "(ローカルタグ未設定)" in win.bookshelf.title_label.text()
    print("[PASS] サイドバーのローカルタグ検索「未設定」検証完了（アイテム2, 4の2件）")

    win.grab().save(os.path.join(artifact_dir, "test_local_tag_unset_sidebar_view.png"))

    # 5. サイドバーのローカルタグ検索欄で「タグなし」入力の検証
    sidebar.local_tag_search_edit.setText("タグなし")
    QApplication.processEvents()
    filtered_ids = [it[0] for it in win.filtered_items]
    assert set(filtered_ids) == {id2, id4}, f"「タグなし」での絞り込み結果不正: {filtered_ids}"
    print("[PASS] サイドバーのローカルタグ検索「タグなし」同義語検証完了")

    # 6. サイドバーのローカルタグ検索欄で通常タグ「ホラー」入力の検証
    sidebar.local_tag_search_edit.setText("ホラー")
    QApplication.processEvents()
    filtered_ids = [it[0] for it in win.filtered_items]
    assert set(filtered_ids) == {id1}, f"ローカルタグ「ホラー」検索結果不正: {filtered_ids} != {[id1]}"
    print("[PASS] サイドバーのローカルタグ通常名「ホラー」検索検証完了（アイテム1のみ）")

    # サイドバーローカル検索をクリア
    sidebar.local_tag_search_edit.clear()
    QApplication.processEvents()

    # 7. 上部ヘッダー検索バーで「タグなし」入力の検証（ユーザー要望：「ローカルタグの検索でもタグがついていないものを絞り込める様に」）
    win.header_bar.search_edit.setText("タグなし")
    # 検索は入力が止まってから反映される（MainWindow.SEARCH_DEBOUNCE_MS）
    QTest.qWait(win.SEARCH_DEBOUNCE_MS + 100)
    filtered_ids = [it[0] for it in win.filtered_items]
    print(f"上部検索バー「タグなし」入力時のアイテムID: {filtered_ids}")
    assert set(filtered_ids) == {id2, id4}, f"上部検索バーでのローカルタグなし絞り込み不正: {filtered_ids} != {[id2, id4]}"
    assert "(ローカルタグ未設定)" in win.bookshelf.title_label.text()
    print("[PASS] 上部ヘッダー検索バー「タグなし」検証完了（アイテム2, 4の2件）")

    win.grab().save(os.path.join(artifact_dir, "test_header_tag_unset_view.png"))

    win.header_bar.search_edit.clear()
    QApplication.processEvents()

    # 8. 組み合わせテスト: グローバルタグ「未設定」 ＋ ローカルタグ検索「未設定」
    QTest.mouseClick(unset_pill, Qt.LeftButton)
    sidebar.local_tag_search_edit.setText("未設定")
    QApplication.processEvents()
    filtered_ids = [it[0] for it in win.filtered_items]
    print(f"G未設定 + L未設定 の組み合わせアイテムID: {filtered_ids}")
    assert set(filtered_ids) == {id4}, f"G未設定 + L未設定 の結果不正: {filtered_ids} != {[id4]}"
    print("[PASS] グローバルタグ未設定 ＋ ローカルタグ未設定の組み合わせ検証完了（アイテム4のみ）")

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

    print("[SUCCESS] 全ての未設定・タグなし絞り込みテストに合格しました！")


if __name__ == "__main__":
    run_tests()
