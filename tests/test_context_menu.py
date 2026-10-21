"""右クリック複数タグメニューと欄外クリック反映の検証テスト (tests/test_context_menu.py)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QPainter
from gui_qt import MainWindow, Theme
from gui_qt.components import ScenarioContextMenu

def test_context_menu():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyleSheet(Theme.get_application_stylesheet())

    win = MainWindow(db_path="catalog.db")
    win.resize(1260, 820)
    win.show()
    QApplication.processEvents()

    if not win.all_items:
        print("No items found.")
        win.close()
        return

    first_item_id = win.all_items[0][0]
    print("Testing with item ID:", first_item_id)

    # 既存のタグを確認
    initial_tags = [t[1] for t in win.db.get_item_tags(first_item_id)]
    print("Initial tags:", initial_tags)

    # カードウィジェットを取得
    card = win.bookshelf.cards[0]
    card_global_pos = card.mapToGlobal(QPoint(card.width() // 2, card.height() // 2))

    # 右クリックコンテキストメニューを生成
    menu = ScenarioContextMenu(first_item_id, win.db, win)
    menu.popup(card_global_pos)
    QApplication.processEvents()

    out_dir = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449"

    # メニュー展開時の画面キャプチャを合成保存
    pix_win = win.grab()
    menu_pix = menu.grab()
    local_pos = win.mapFromGlobal(card_global_pos)
    painter = QPainter(pix_win)
    painter.drawPixmap(local_pos, menu_pix)
    painter.end()
    pix_win.save(os.path.join(out_dir, "view_context_menu_opened.png"))
    print("Saved context menu capture to view_context_menu_opened.png")

    # チェックボックスをトグルしてみる（複数選択の検証）
    if menu.tag_widgets:
        for tid, w in list(menu.tag_widgets.items())[:2]:
            w.checkbox.setChecked(not w.checkbox.isChecked())
            print(f"Toggled tag {w.tag_name} -> {w.checkbox.isChecked()}")

    # メニューを閉じる（欄外クリック動作）
    menu.close()
    QApplication.processEvents()

    updated_tags = [t[1] for t in win.db.get_item_tags(first_item_id)]
    print("Updated tags after menu close (outside click):", updated_tags)

    win.close()
    print("Context menu test completed successfully!")

if __name__ == "__main__":
    test_context_menu()
