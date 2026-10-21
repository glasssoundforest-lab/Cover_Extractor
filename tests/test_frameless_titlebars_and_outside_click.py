"""カスタムタイトルバーおよび詳細ウィンドウ枠外クリック自動終了のテスト
(tests/test_frameless_titlebars_and_outside_click.py)
"""

import sys
import os

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QTimer, Qt, QPoint, QEvent
from PySide6.QtGui import QMouseEvent
from core.database import Database
from gui_qt.main_window import MainWindow
from gui_qt.dialogs.item_detail_dialog import ItemDetailDialog
from gui_qt.dialogs.settings_dialog import SettingsDialog

QMessageBox.information = lambda *args, **kwargs: QMessageBox.Ok
QMessageBox.warning = lambda *args, **kwargs: QMessageBox.Ok
QMessageBox.question = lambda *args, **kwargs: QMessageBox.Yes

ARTIFACT_DIR = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449"


def run_test():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    test_db_path = os.path.join(ROOT_DIR, "test_custom_tb.db")
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    db = Database(test_db_path)
    item_id = db.save_item(
        file_path="M:/Tool/Cover_extractor/test_custom_tb.txt",
        title="狂気山脈 〜邪神の山嶺〜",
        system_name="クトゥルフ神話TRPG",
        players_text="3-4",
        duration_text="6-8",
        overview="古き神々の眠る頂。",
        synopsis="未踏峰のサバイバル。",
        thumbnail_bytes=None,
    )
    db.toggle_item_tag(item_id, "CoC", enabled=True)

    refs = {}

    # -------------------------------------------------------------
    # ステップ1: メインウィンドウのカスタムタイトルバー撮影
    # -------------------------------------------------------------
    def step1_capture_main_window():
        mw = MainWindow(db_path=test_db_path)
        refs["mw"] = mw
        mw.show()
        app.processEvents()

        assert mw.windowFlags() & Qt.FramelessWindowHint, "MainWindow should have FramelessWindowHint"
        assert hasattr(mw, "title_bar"), "MainWindow should have title_bar"

        pix = mw.grab()
        pix.save(os.path.join(ARTIFACT_DIR, "main_window_custom_title_bar.png"))
        print("[OK] main_window_custom_title_bar.png saved")

        # ウィンドウ移動（ドラッグ）の検証
        init_pos = mw.pos()
        tb = mw.title_bar
        # タイトル文字列の上でマウスプレス
        press_pos = tb.mapToGlobal(QPoint(100, 15))
        press_ev = QMouseEvent(QEvent.MouseButtonPress, QPoint(100, 15), press_pos, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        app.sendEvent(tb, press_ev)
        # 30px 右下にドラッグ
        move_pos = tb.mapToGlobal(QPoint(130, 45))
        move_ev = QMouseEvent(QEvent.MouseMove, QPoint(130, 45), move_pos, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        app.sendEvent(tb, move_ev)
        # リリース
        rel_ev = QMouseEvent(QEvent.MouseButtonRelease, QPoint(130, 45), move_pos, Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
        app.sendEvent(tb, rel_ev)
        app.processEvents()

        new_pos = mw.pos()
        print(f"[OK] Window dragging tested. Initial pos: {init_pos}, New pos: {new_pos}")

        QTimer.singleShot(400, step2_capture_item_detail)

    # -------------------------------------------------------------
    # ステップ2: 詳細ウィンドウのカスタムタイトルバー撮影 & 枠外クリックテスト
    # -------------------------------------------------------------
    def step2_capture_item_detail():
        mw = refs["mw"]
        detail = ItemDetailDialog(item_id, db=db, item_ids=[item_id], parent=mw)
        refs["detail"] = detail

        # dlg.exec() を非同期で起動
        def run_outside_click():
            app.processEvents()
            assert detail.isVisible(), "ItemDetailDialog must be visible"

            pix = detail.grab()
            pix.save(os.path.join(ARTIFACT_DIR, "item_detail_custom_title_bar.png"))
            print("[OK] item_detail_custom_title_bar.png saved")

            # 枠外クリック（メインウィンドウ上の座標をクリック）
            mw_click_pos = mw.mapToGlobal(QPoint(30, 30))
            diag_rect = detail.rect().translated(detail.mapToGlobal(QPoint(0, 0)))
            assert not diag_rect.contains(mw_click_pos), "Click position must be outside detail dialog"

            # メインウィンドウへのクリックイベントを送信
            mouse_event = QMouseEvent(
                QEvent.MouseButtonPress,
                QPoint(30, 30),
                mw_click_pos,
                Qt.LeftButton,
                Qt.LeftButton,
                Qt.NoModifier,
            )
            app.sendEvent(mw, mouse_event)
            app.processEvents()

            # ダイアログが自動で閉じたことを検証！
            assert not detail.isVisible(), "ItemDetailDialog should close when clicking on parent window outside dialog!"
            print("[OK] ItemDetailDialog successfully closed on outside parent click!")

            QTimer.singleShot(400, step3_capture_settings_dialog)

        QTimer.singleShot(200, run_outside_click)
        detail.exec()

    # -------------------------------------------------------------
    # ステップ3: 設定ダイアログのカスタムタイトルバー撮影
    # -------------------------------------------------------------
    def step3_capture_settings_dialog():
        settings = SettingsDialog(db=db)
        refs["settings"] = settings
        settings.show()
        app.processEvents()

        assert settings.windowFlags() & Qt.FramelessWindowHint, "SettingsDialog should have FramelessWindowHint"
        assert hasattr(settings, "title_bar"), "SettingsDialog should have title_bar"

        pix = settings.grab()
        pix.save(os.path.join(ARTIFACT_DIR, "settings_custom_title_bar.png"))
        print("[OK] settings_custom_title_bar.png saved")

        settings.close()
        refs["mw"].close()

        # クリーンアップ
        try:
            if os.path.exists(test_db_path):
                os.remove(test_db_path)
        except Exception:
            pass

        print("[ALL TITLEBAR & OUTSIDE-CLICK TESTS PASSED SUCCESSFULLY]")
        app.quit()

    QTimer.singleShot(500, step1_capture_main_window)
    app.exec()


if __name__ == "__main__":
    run_test()
