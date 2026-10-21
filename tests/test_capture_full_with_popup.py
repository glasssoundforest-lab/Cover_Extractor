import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPainter, QImage

from core.database import Database
from gui_qt.main_window import MainWindow

def capture_composite():
    app = QApplication.instance() or QApplication(sys.argv)
    test_db_path = "test_composite.db"
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    db = Database(test_db_path)
    db.add_tag("CoC", is_global=1)
    db.add_tag("マダミス", is_global=1)
    db.add_tag("未通過", is_global=1)
    db.add_tag("通過済み", is_global=1)
    db.add_tag("ホラー", is_global=0)
    db.add_tag("洋館", is_global=0)

    win = MainWindow(db_path=test_db_path)
    win.resize(1260, 800)
    win.show()
    QApplication.processEvents()

    hbar = win.header_bar
    hbar._toggle_tag_popup()
    QApplication.processEvents()

    # メインウィンドウ画像を取得
    win_pix = win.grab()
    popup_pix = hbar.tag_popup.grab()

    # ポップアップの相対座標
    gp = hbar.tag_select_btn.mapToGlobal(QPoint(0, hbar.tag_select_btn.height() + 2))
    win_gp = win.mapToGlobal(QPoint(0, 0))
    rel_x = gp.x() - win_gp.x()
    rel_y = gp.y() - win_gp.y()

    # 合成画像を作成
    composite = win_pix.copy()
    painter = QPainter(composite)
    painter.drawPixmap(rel_x, rel_y, popup_pix)
    painter.end()

    artifact_dir = os.environ.get("ANTIGRAVITY_ARTIFACT_DIR", r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449")
    composite.save(os.path.join(artifact_dir, "centered_header_with_tag_popup_composite.png"))

    hbar.tag_popup.hide()
    win.close()
    try:
        db.conn.close()
        if hasattr(win, "db") and win.db:
            win.db.conn.close()
    except Exception:
        pass
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

if __name__ == "__main__":
    capture_composite()
