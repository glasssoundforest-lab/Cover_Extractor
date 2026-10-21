"""タグ編集（10色プリセット＋自由調色領域）機能の自動テストおよびスクリーンショット撮影
(tests/test_tag_edit_color.py)
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
from gui_qt.dialogs.settings_dialog import SettingsDialog, TagEditDialog
from gui_qt.main_window import MainWindow

QMessageBox.information = lambda *args, **kwargs: QMessageBox.Ok
QMessageBox.warning = lambda *args, **kwargs: QMessageBox.Ok
QMessageBox.question = lambda *args, **kwargs: QMessageBox.Yes

ARTIFACT_DIR = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449"

def run_test():
    app = QApplication.instance() or QApplication(sys.argv)

    src_db = os.path.join(ROOT_DIR, "catalog.db")
    test_db_path = os.path.join(ROOT_DIR, "test_tag_edit_color.db")
    if os.path.exists(src_db):
        shutil.copy2(src_db, test_db_path)

    db = Database(test_db_path)

    # テスト用タグを追加しておく（「長編シナリオ」深緑色）
    test_tid = db.add_tag("長編シナリオ", color="#1b5e20")

    dlg = SettingsDialog(db=db)
    dlg.show()
    app.processEvents()

    edit_dialog_ref = [None]
    main_window_ref = [None]

    def step1_capture_settings_with_colors():
        """ステップ1: タグ一覧に色アイコンと『✎ タグの編集...』ボタンが表示されている状態を撮影"""
        dlg._load_tags_table(select_tag_id=test_tid)
        app.processEvents()

        pix = dlg.grab()
        pix.save(os.path.join(ARTIFACT_DIR, "settings_tags_tab_with_color.png"))
        print("[OK] settings_tags_tab_with_color.png saved")

        QTimer.singleShot(400, step2_open_edit_dialog)

    def step2_open_edit_dialog():
        """ステップ2: タグ編集ダイアログを開き、10色プリセット＋自由調色領域が表示されている状態を撮影"""
        row = dlg.tag_table.currentRow()
        item = dlg.tag_table.item(row, 1)
        tid = item.data(Qt.UserRole)
        name = item.data(Qt.UserRole + 1)
        color = item.data(Qt.UserRole + 2)

        edit_dlg = TagEditDialog(tid, name, color, db, parent=dlg)
        edit_dialog_ref[0] = edit_dlg
        edit_dlg.show()
        app.processEvents()

        # 10色プリセットから琥珀色 (#b8621b) を選択
        edit_dlg.name_edit.setText("大作長編")
        edit_dlg._select_preset_color("#b8621b")
        app.processEvents()

        pix = edit_dlg.grab()
        pix.save(os.path.join(ARTIFACT_DIR, "tag_edit_dialog_presets.png"))
        print("[OK] tag_edit_dialog_presets.png saved")

        QTimer.singleShot(400, step2b_adjust_custom_color)

    def step2b_adjust_custom_color():
        """ステップ2b: 自由調色領域でスライダーを動かして独自カスタムカラーを作成した状態を撮影"""
        edit_dlg = edit_dialog_ref[0]

        # 自由調色領域で R, G, B を調整 (例: 秘術エメラルド #279e68 -> R: 39, G: 158, B: 104)
        edit_dlg.r_slider.setValue(39)
        edit_dlg.g_slider.setValue(158)
        edit_dlg.b_slider.setValue(104)
        app.processEvents()

        pix = edit_dlg.grab()
        pix.save(os.path.join(ARTIFACT_DIR, "tag_edit_dialog_custom_color.png"))
        print("[OK] tag_edit_dialog_custom_color.png saved")

        QTimer.singleShot(400, step3_save_edit)

    def step3_save_edit():
        """ステップ3: 編集を保存し、設定ダイアログのテーブルに新しい名前・色が反映された状態を撮影"""
        edit_dlg = edit_dialog_ref[0]
        if edit_dlg:
            edit_dlg._on_save()
            edit_dlg.close()

        dlg._load_tags_table(select_tag_id=test_tid)
        app.processEvents()

        pix = dlg.grab()
        pix.save(os.path.join(ARTIFACT_DIR, "settings_tags_tab_custom_saved.png"))
        print("[OK] settings_tags_tab_custom_saved.png saved")

        QTimer.singleShot(400, step4_test_sidebar_color_sync)

    def step4_test_sidebar_color_sync():
        """ステップ4: メインウィンドウのサイドバーにしおりタグの色が正しく同期反映されているか撮影"""
        dlg.close()

        mw = MainWindow(db_path=test_db_path)
        main_window_ref[0] = mw
        mw.show()
        app.processEvents()

        pix = mw.grab()
        pix.save(os.path.join(ARTIFACT_DIR, "main_sidebar_custom_color_sync.png"))
        print("[OK] main_sidebar_custom_color_sync.png saved")

        # 終了クリーンアップ
        mw.close()
        try:
            if os.path.exists(test_db_path):
                os.remove(test_db_path)
        except Exception:
            pass
        app.quit()

    QTimer.singleShot(500, step1_capture_settings_with_colors)
    app.exec()

if __name__ == "__main__":
    run_test()
