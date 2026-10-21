"""しおり・お気に入り・グローバルタグの分離とピル型ボタン統一の検証テスト

検証項目:
1. サイドバーが「システム分類」「お気に入り」「しおり」「タグ」の4セクションに独立分離していること
2. サイドバーのタグセクションにはグローバルタグのみが表示され、ローカルタグは含まれないこと
3. タグの表記が長方形の短辺が丸いボタン（PillTag）に統一されていること
4. お気に入り、しおりのフィルタリングがそれぞれ正常に動作すること
5. 詳細画面のタグ表示枠も長方形の短辺が丸いボタン（PillTag）で統一表示されていること
6. 詳細画面で「しおりを挟む/外す」操作、バッジ表示が連動すること
"""

import os
import sys

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap, QImage, QColor

from core.database import Database
from gui_qt.main_window import MainWindow
from gui_qt.components.sidebar import PillCategoryButton
from gui_qt.components.ornate import PillTag
from gui_qt.dialogs.item_detail_dialog import ItemDetailDialog


def run_tests():
    app = QApplication.instance() or QApplication(sys.argv)

    # 1. テスト用インメモリDBのセットアップ
    test_db_path = "test_separated_pills.db"
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    db = Database(test_db_path)

    # グローバルタグとローカルタグの追加
    # グローバル
    tid_coc = db.add_tag("CoC", is_global=1)
    tid_mm = db.add_tag("マダミス", is_global=1)
    tid_unp = db.add_tag("未通過", is_global=1)
    tid_pas = db.add_tag("通過済み", is_global=1)
    tid_gm = db.add_tag("GM可", is_global=1)

    # ローカル
    tid_horror = db.add_tag("ホラー", is_global=0)
    tid_mansion = db.add_tag("洋館", is_global=0)
    tid_duo = db.add_tag("タイマン", is_global=0)

    # ダミーサムネイル画像
    img = QImage(260, 180, QImage.Format_RGB32)
    img.fill(QColor("#3a2a1a"))
    from PySide6.QtCore import QBuffer, QIODevice
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    thumb_data = bytes(buf.data())

    # アイテム追加
    # アイテム1: CoC, favorite=1, bookmarked=1
    id1 = db.save_item(
        file_path="scenario1.pdf",
        title="狂気山脈 〜邪神の山嶺〜",
        system_name="CoC",
        players_text="3-4人",
        duration_text="6時間",
        overview="登山と狂気のクトゥルフ神話TRPGシナリオ。",
        synopsis="吹雪吹きすさぶ未踏峰。そこに眠る太古の秘密とは。",
        thumbnail_bytes=thumb_data,
    )
    db.set_favorite(id1, True)
    db.set_bookmarked(id1, True)
    db.toggle_item_tag(id1, "CoC", enabled=True)
    db.toggle_item_tag(id1, "未通過", enabled=True)
    db.toggle_item_tag(id1, "ホラー", enabled=True)

    # アイテム2: マダミス, favorite=0, bookmarked=1
    id2 = db.save_item(
        file_path="scenario2.pdf",
        title="J・モリアーティの暗躍",
        system_name="マダミス",
        players_text="5人",
        duration_text="3時間",
        overview="ベーカー街を舞台にした推理マーダーミステリー。",
        synopsis="霧深きロンドンで起こる不可解な事件。",
        thumbnail_bytes=thumb_data,
    )
    db.set_bookmarked(id2, True)
    db.toggle_item_tag(id2, "マダミス", enabled=True)
    db.toggle_item_tag(id2, "通過済み", enabled=True)
    db.toggle_item_tag(id2, "洋館", enabled=True)

    # アイテム3: CoC, favorite=1, bookmarked=0
    id3 = db.save_item(
        file_path="scenario3.pdf",
        title="カタシロ",
        system_name="CoC",
        players_text="1人",
        duration_text="1時間",
        overview="対話型クトゥルフ神話TRPGシナリオ。",
        synopsis="病室で目覚めたあなたを待つもの。",
        thumbnail_bytes=thumb_data,
    )
    db.set_favorite(id3, True)
    db.toggle_item_tag(id3, "CoC", enabled=True)
    db.toggle_item_tag(id3, "通過済み", enabled=True)
    db.toggle_item_tag(id3, "タイマン", enabled=True)

    # 2. メインウィンドウの起動とサイドバー検証
    win = MainWindow(db_path=test_db_path)
    win.resize(1100, 750)
    win.show()
    QApplication.processEvents()

    # サイドバーのセクションとピルボタン検証
    sidebar = win.sidebar

    # 2.1 お気に入り・しおり独立ボタンの検証
    assert hasattr(sidebar, "fav_button"), "fav_buttonが存在しません"
    assert hasattr(sidebar, "bm_button"), "bm_buttonが存在しません"
    assert isinstance(sidebar.fav_button, PillCategoryButton), "fav_buttonがPillCategoryButtonではありません"
    assert isinstance(sidebar.bm_button, PillCategoryButton), "bm_buttonがPillCategoryButtonではありません"
    assert sidebar.fav_button.count == 2, f"お気に入り件数が正しくありません: {sidebar.fav_button.count} != 2"
    assert sidebar.bm_button.count == 2, f"しおり件数が正しくありません: {sidebar.bm_button.count} != 2"
    print("[PASS] サイドバーのお気に入り(2件)・しおり(2件)独立ボタン検証完了")

    # 2.2 グローバルタグのみが表示されていることの検証
    tag_names_in_sidebar = list(sidebar.tag_widgets.keys())
    print(f"サイドバーのタグ一覧: {tag_names_in_sidebar}")
    # グローバルタグのみ含まれること
    for gtag in ["CoC", "マダミス", "未通過", "通過済み", "GM可"]:
        assert gtag in tag_names_in_sidebar, f"グローバルタグ {gtag} がサイドバーにありません"
    # ローカルタグが含まれていないこと
    for ltag in ["ホラー", "洋館", "タイマン"]:
        assert ltag not in tag_names_in_sidebar, f"ローカルタグ {ltag} がサイドバーに含まれてしまっています"
    print("[PASS] サイドバーのタグセクションはグローバルタグのみ表示（ローカルタグ除外）検証完了")

    # 2.3 タグウィジェットがPillTag（短辺丸型ボタン）であることの検証
    for tname, widget in sidebar.tag_widgets.items():
        assert isinstance(widget, PillTag), f"{tname} ウィジェットが PillTag ではありません"
    print("[PASS] サイドバーの全タグが PillTag（短辺丸型ボタン）に統一されていることを確認")

    # 3. フィルタリング動作の検証
    # 3.1 「★ お気に入り」でフィルタ
    sidebar.fav_button.clicked.emit("__favorite__")
    QApplication.processEvents()
    disp_ids = [it[0] for it in win.filtered_items]
    assert disp_ids == [id3, id1] or disp_ids == [id1, id3], f"お気に入り絞り込み結果不正: {disp_ids}"
    assert "★ お気に入り" in win.bookshelf.title_label.text(), f"見出し不正: {win.bookshelf.title_label.text()}"
    print("[PASS] お気に入りフィルタリング検証完了（アイテム1, 3の2件表示）")

    # キャプチャ保存
    artifact_dir = os.environ.get("ANTIGRAVITY_ARTIFACT_DIR", r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449")
    fav_pix = win.grab()
    fav_pix.save(os.path.join(artifact_dir, "test_favorite_filter_view.png"))

    # 3.2 「🔖 しおり」でフィルタ
    sidebar.bm_button.clicked.emit("__bookmarked__")
    QApplication.processEvents()
    disp_ids = [it[0] for it in win.filtered_items]
    assert disp_ids == [id2, id1] or disp_ids == [id1, id2], f"しおり絞り込み結果不正: {disp_ids}"
    assert "🔖 しおり" in win.bookshelf.title_label.text(), f"見出し不正: {win.bookshelf.title_label.text()}"
    print("[PASS] しおりフィルタリング検証完了（アイテム1, 2の2件表示）")

    bm_pix = win.grab()
    bm_pix.save(os.path.join(artifact_dir, "test_bookmark_filter_view.png"))

    # 3.3 「すべて」に戻してサイドバー全体キャプチャ
    sidebar.system_widgets["すべて"].clicked.emit("すべて")
    QApplication.processEvents()
    main_pix = win.grab()
    main_pix.save(os.path.join(artifact_dir, "test_sidebar_separated_view.png"))

    # 4. 詳細画面（ItemDetailDialog）のピル型タグ枠＆しおり機能検証
    detail_dlg = ItemDetailDialog(item_id=id1, db=db, parent=win)
    detail_dlg.show()
    QApplication.processEvents()

    # 4.1 しおりボタンとお気に入りボタンの表示確認
    assert detail_dlg.is_favorite == True
    assert detail_dlg.is_bookmarked == True
    assert "お気に入り" in detail_dlg.fav_toggle_btn.text()
    assert "しおり中" in detail_dlg.bm_toggle_btn.text()
    assert detail_dlg.fav_badge.isVisible()
    assert detail_dlg.bm_badge.isVisible()
    print("[PASS] 詳細画面の初期バッジ・ボタン状態検証完了（お気に入り中・しおり中）")

    # 4.2 タグ枠内のPillTag統一検証
    # tags_container のレイアウト内を走査して PillTag の存在を確認
    found_pill_tags = []
    for i in range(detail_dlg.tags_flow_layout.count()):
        item = detail_dlg.tags_flow_layout.itemAt(i)
        if item.widget() and isinstance(item.widget(), PillTag):
            found_pill_tags.append(item.widget().text)
        elif item.layout():
            for j in range(item.layout().count()):
                sub = item.layout().itemAt(j)
                if sub.widget() and isinstance(sub.widget(), PillTag):
                    found_pill_tags.append(sub.widget().text)
    print(f"詳細画面のピルタグ: {found_pill_tags}")
    assert "CoC" in found_pill_tags
    assert "未通過" in found_pill_tags
    assert "ホラー" in found_pill_tags
    print("[PASS] 詳細画面のタグ枠が長方形短辺丸型ボタン（PillTag）で統一配置されていることを確認")

    # 4.3 詳細画面でのしおりトグル操作検証
    detail_dlg._toggle_bookmarked()
    QApplication.processEvents()
    assert detail_dlg.is_bookmarked == False
    assert "しおりを挟む" in detail_dlg.bm_toggle_btn.text()
    assert not detail_dlg.bm_badge.isVisible()
    assert db.get_bookmarked(id1) == 0
    print("[PASS] 詳細画面でのしおり解除トグル検証完了")

    # 再度しおりを挟む
    detail_dlg._toggle_bookmarked()
    QApplication.processEvents()
    assert detail_dlg.is_bookmarked == True
    assert "しおり中" in detail_dlg.bm_toggle_btn.text()
    assert detail_dlg.bm_badge.isVisible()
    assert db.get_bookmarked(id1) == 1
    print("[PASS] 詳細画面でのしおり追加トグル検証完了")

    # 詳細画面キャプチャ
    detail_pix = detail_dlg.grab()
    detail_pix.save(os.path.join(artifact_dir, "test_item_detail_pill_tags.png"))

    detail_dlg.close()
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

    print("[SUCCESS] 全てのテスト（しおり・タグ分離・ピル型ボタン統一）に合格しました！")


if __name__ == "__main__":
    run_tests()
