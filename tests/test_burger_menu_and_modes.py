"""バーガーメニューおよび大・中・小・2カラム一覧表示の検証テスト
"""

import sys
import os

# プロジェクトルートを追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPoint
from gui_qt import MainWindow, Theme

def test_burger_and_modes():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyleSheet(Theme.get_application_stylesheet())

    win = MainWindow(db_path="catalog.db")
    win.resize(1260, 800)
    win.show()

    # テスト用にアイテムが1件のみの場合、複数件ある状態での2カラム表示を確認するため
    # 既存アイテムを複製してダミーアイテムを数件追加して表示確認
    if len(win.all_items) == 1:
        base_it = win.all_items[0]
        # (id, file_path, title, system_name, players_text, duration_text, overview, synopsis, thumbnail)
        dummy_items = [
            (1, base_it[1], "共犯者", "マーダーミステリー", "6人", "4時間", "ある企業のグループに所属する6人の男女は、ある事件の調査のために集められた…", "共犯者たちによるマーダーミステリー", base_it[8]),
            (2, "dummy_2", "海も枯れるまで", "クトゥルフ神話TRPG", "2人", "6〜8時間", "深く碧い海の底で、君と僕が見た世界の真実とは…", "名作CoCシナリオ", None),
            (3, "dummy_3", "狂気山脈 〜邪神の山嶺〜", "クトゥルフ神話TRPG", "3〜4人", "5時間", "未踏峰の雪山に挑む探索者たち。そこに眠る狂気の遺構…", "雪山登山CoCシナリオ", None),
            (4, "dummy_4", "新約・コウフク論", "エモクロアTRPG", "2〜3人", "3時間", "幸福とは何かを問いかける現代エモクロアシナリオ。", "エモクロア公式", None),
        ]
        win.all_items = dummy_items
        win._filter_and_display()

    QApplication.processEvents()

    out_dir = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449"

    # 1. デフォルト: 「中」表示モードのキャプチャ
    pix_med = win.grab()
    pix_med.save(os.path.join(out_dir, "view_mode_medium.png"))
    print("Captured Medium mode.")

    # 2. 一覧（2カラム）表示モードのキャプチャ
    win.bookshelf.set_view_mode("list")
    QApplication.processEvents()
    pix_list = win.grab()
    pix_list.save(os.path.join(out_dir, "view_mode_list_2col.png"))
    print("Captured List (2-column) mode.")

    # 3. 大表示モードのキャプチャ
    win.bookshelf.set_view_mode("large")
    QApplication.processEvents()
    pix_large = win.grab()
    pix_large.save(os.path.join(out_dir, "view_mode_large.png"))
    print("Captured Large mode.")

    # 4. 小表示モードのキャプチャ
    win.bookshelf.set_view_mode("small")
    QApplication.processEvents()
    pix_small = win.grab()
    pix_small.save(os.path.join(out_dir, "view_mode_small.png"))
    print("Captured Small mode.")

    # 5. バーガーメニューを開いた状態のキャプチャ
    win.bookshelf.set_view_mode("medium")
    win.header_bar.act_medium.setChecked(True)
    # バーガーメニューを開く
    menu_width = win.header_bar.menu.sizeHint().width()
    pos = win.header_bar.burger_btn.mapToGlobal(QPoint(win.header_bar.burger_btn.width() - menu_width, 32))
    win.header_bar.menu.popup(pos)
    QApplication.processEvents()

    from PySide6.QtGui import QPainter
    pix_menu = win.grab()
    menu_pix = win.header_bar.menu.grab()
    local_pos = win.mapFromGlobal(pos)
    painter = QPainter(pix_menu)
    painter.drawPixmap(local_pos, menu_pix)
    painter.end()

    pix_menu.save(os.path.join(out_dir, "view_burger_menu_opened.png"))
    win.header_bar.menu.close()
    print("Captured Burger Menu opened.")

    win.close()
    print("All view mode tests completed successfully!")

if __name__ == "__main__":
    test_burger_and_modes()
