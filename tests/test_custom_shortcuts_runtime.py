"""変更されたショートカットキーによる詳細画面のランタイム動作テスト (tests/test_custom_shortcuts_runtime.py)
"""

import sys
import os

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from core.database import Database
from gui_qt.dialogs.item_detail_dialog import ItemDetailDialog
import app_settings

def run_test():
    app = QApplication.instance() or QApplication(sys.argv)

    # カスタムショートカットを設定（例: 前へ='A', 次へ='D', お気に入り='T'）
    custom_sc = {
        "detail_prev": "A",
        "detail_next": "D",
        "detail_favorite": "T",
        "detail_edit": "E",
        "detail_close": "Esc",
        "main_search": "Ctrl+F",
        "main_open": "Return",
    }
    app_settings.save_all_shortcuts(custom_sc)

    db = Database("catalog.db")
    items = db.get_items()
    item_ids = [it[0] for it in items]

    dlg = ItemDetailDialog(item_ids[0], db, item_ids=item_ids)
    dlg.show()
    app.processEvents()

    assert dlg.current_index == 0, "Initial index should be 0"

    # 'D' キーのイベントをシミュレート（次の書物へめくる）
    ev_d = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_D, Qt.NoModifier, "d")
    dlg.keyPressEvent(ev_d)
    assert dlg.current_index == 1, f"Expected index 1 after pressing D, got {dlg.current_index}"
    print("[OK] Pressed 'D' -> turned to next book (index 1)")

    # 'A' キーのイベントをシミュレート（前の書物へめくる）
    ev_a = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_A, Qt.NoModifier, "a")
    dlg.keyPressEvent(ev_a)
    assert dlg.current_index == 0, f"Expected index 0 after pressing A, got {dlg.current_index}"
    print("[OK] Pressed 'A' -> turned back to first book (index 0)")

    # 'T' キーのイベントをシミュレート（お気に入りトグル）
    initial_fav = dlg.is_favorite
    ev_t = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_T, Qt.NoModifier, "t")
    dlg.keyPressEvent(ev_t)
    assert dlg.is_favorite != initial_fav, "Expected favorite to toggle after pressing T"
    print(f"[OK] Pressed 'T' -> favorite toggled to {dlg.is_favorite}")

    # もう一度 'T' で元に戻す
    dlg.keyPressEvent(ev_t)
    assert dlg.is_favorite == initial_fav, "Expected favorite to revert"
    print("[OK] Favorite reverted back")

    # ショートカットをデフォルトに戻す
    app_settings.save_all_shortcuts(app_settings.DEFAULT_SHORTCUTS)
    print("[OK] Restored default shortcuts")

    dlg.close()
    app.quit()

if __name__ == "__main__":
    run_test()
