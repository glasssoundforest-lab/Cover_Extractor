"""グローバルタグ・ローカルタグ分離機能の自動テストおよびUIキャプチャ撮影
(tests/test_global_local_tags.py)
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
from gui_qt.components.tag_context_menu import ScenarioContextMenu
from gui_qt.dialogs.item_detail_dialog import ItemDetailDialog, MultiTagEditDialog
from gui_qt.dialogs.settings_dialog import SettingsDialog, TagEditDialog

# ダイアログのブロッキング抑止
QMessageBox.information = lambda *args, **kwargs: QMessageBox.Ok
QMessageBox.warning = lambda *args, **kwargs: QMessageBox.Ok
QMessageBox.question = lambda *args, **kwargs: QMessageBox.Yes

ARTIFACT_DIR = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449"


def run_test():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    test_db_path = os.path.join(ROOT_DIR, "test_global_local.db")
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    db = Database(test_db_path)

    # 1. 初期グローバルタグの確認
    gtags = db.get_global_tags()
    gnames = [t[1] for t in gtags]
    print(f"[OK] Initial global tags in DB: {gnames}")
    assert "CoC" in gnames
    assert "マダミス" in gnames
    assert "未通過" in gnames
    assert "通過済み" in gnames
    assert "GM可" in gnames

    # 2. テスト用アイテムとローカルタグの登録
    item_id = db.save_item(
        file_path="M:/Tool/Cover_extractor/sample_scenario.txt",
        title="狂気山脈 〜邪神の山嶺〜",
        system_name="クトゥルフ神話TRPG",
        players_text="3-4",
        duration_text="6-8",
        overview="狂気山脈へと挑む登山家探索者たちの極限サバイバル。",
        synopsis="未踏峰の頂に待つのは神秘か、それとも破滅か。",
        thumbnail_bytes=None,
    )

    # グローバルタグ「CoC」「未通過」とローカルタグ「登山隊」「第1話」を登録
    db.toggle_item_tag(item_id, "CoC", enabled=True)
    db.toggle_item_tag(item_id, "未通過", enabled=True)
    db.add_tag("登山隊", color="#795548", is_global=0)
    db.add_tag("第1話", color="#546e7a", is_global=0)
    db.toggle_item_tag(item_id, "登山隊", enabled=True)

    # 保存されているタグの検証
    item_gtags = [t[1] for t in db.get_item_tags(item_id, is_global=True)]
    item_ltags = [t[1] for t in db.get_item_tags(item_id, is_global=False)]
    print(f"[OK] Item global tags: {item_gtags}")
    print(f"[OK] Item local tags: {item_ltags}")
    assert "CoC" in item_gtags and "未通過" in item_gtags
    assert "登山隊" in item_ltags

    # -------------------------------------------------------------
    # UI キャプチャの流れ
    # -------------------------------------------------------------
    refs = {}

    def step1_capture_context_menu():
        """右クリックメニューのキャプチャ（グローバルタグ選択）"""
        menu = ScenarioContextMenu(item_id, db)
        refs["menu"] = menu
        menu.show()
        app.processEvents()

        # メニューのサイズが確定するように少し待つ
        pix = menu.grab()
        pix.save(os.path.join(ARTIFACT_DIR, "context_menu_global_tags.png"))
        print("[OK] context_menu_global_tags.png saved")

        menu.close()
        QTimer.singleShot(400, step2_capture_item_detail)

    def step2_capture_item_detail():
        """シナリオ詳細画面のキャプチャ（グローバルとローカルの分離表示）"""
        detail = ItemDetailDialog(item_id, db=db, item_ids=[item_id])
        refs["detail"] = detail
        detail.show()
        app.processEvents()

        pix = detail.grab()
        pix.save(os.path.join(ARTIFACT_DIR, "item_detail_tags_separated.png"))
        print("[OK] item_detail_tags_separated.png saved")

        # 編集モードにして「ローカルタグを編集」を開く
        detail._toggle_edit_mode()
        app.processEvents()

        loc_dlg = MultiTagEditDialog(item_id, db, parent=detail)
        refs["loc_dlg"] = loc_dlg
        loc_dlg.show()
        app.processEvents()

        # 新しいローカルタグを追加
        loc_dlg.new_tag_in.setText("雪山遭難")
        loc_dlg._add_new_tag()
        app.processEvents()

        pix2 = loc_dlg.grab()
        pix2.save(os.path.join(ARTIFACT_DIR, "multi_tag_edit_dialog_local.png"))
        print("[OK] multi_tag_edit_dialog_local.png saved")

        loc_dlg.accept()
        app.processEvents()

        detail.close()
        QTimer.singleShot(400, step3_capture_settings_global_tab)

    def step3_capture_settings_global_tab():
        """設定画面: グローバルタグ編集画面のキャプチャ"""
        settings = SettingsDialog(db=db)
        refs["settings"] = settings
        settings.show()
        app.processEvents()

        # グローバルタグサブタブ (index 0)
        settings.tag_sub_tabs.setCurrentIndex(0)
        app.processEvents()

        pix = settings.grab()
        pix.save(os.path.join(ARTIFACT_DIR, "settings_global_tags_tab.png"))
        print("[OK] settings_global_tags_tab.png saved")

        QTimer.singleShot(400, step4_capture_settings_local_tab)

    def step4_capture_settings_local_tab():
        """設定画面: ローカルタグ編集画面のキャプチャ"""
        settings = refs["settings"]

        # ローカルタグサブタブ (index 1) に切り替え
        settings.tag_sub_tabs.setCurrentIndex(1)
        app.processEvents()

        pix = settings.grab()
        pix.save(os.path.join(ARTIFACT_DIR, "settings_local_tags_tab.png"))
        print("[OK] settings_local_tags_tab.png saved")

        QTimer.singleShot(400, step5_capture_tag_edit_dialog)

    def step5_capture_tag_edit_dialog():
        """タグ編集ダイアログ（is_globalチェックボックス付き）のキャプチャ"""
        settings = refs["settings"]
        # ローカルタグの先頭行を選択して編集ダイアログを開く
        table = settings.local_tag_table
        if table.rowCount() > 0:
            table.selectRow(0)
            item = table.item(0, 1)
            tid = item.data(Qt.UserRole)
            name = item.data(Qt.UserRole + 1)
            color = item.data(Qt.UserRole + 2)
            is_glob = item.data(Qt.UserRole + 3)

            dlg = TagEditDialog(tid, name, color, db, is_global=is_glob, parent=settings)
            refs["edit_dlg"] = dlg
            dlg.show()
            app.processEvents()

            pix = dlg.grab()
            pix.save(os.path.join(ARTIFACT_DIR, "tag_edit_dialog_global_check.png"))
            print("[OK] tag_edit_dialog_global_check.png saved")

            dlg.close()

        settings.close()

        # クリーンアップ
        try:
            if os.path.exists(test_db_path):
                os.remove(test_db_path)
        except Exception:
            pass

        print("[ALL TESTS PASSED SUCCESSFULLY]")
        app.quit()

    QTimer.singleShot(500, step1_capture_context_menu)
    app.exec()


if __name__ == "__main__":
    run_test()
