import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from core.database import Database
from gui_qt.main_window import MainWindow

def capture_popup():
    app = QApplication.instance() or QApplication(sys.argv)
    test_db_path = "test_popup_cap.db"
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    db = Database(test_db_path)
    db.add_tag("CoC", is_global=1)
    db.add_tag("マダミス", is_global=1)
    db.add_tag("未通過", is_global=1)
    db.add_tag("ホラー", is_global=0)
    db.add_tag("洋館", is_global=0)

    win = MainWindow(db_path=test_db_path)
    win.show()
    QApplication.processEvents()

    hbar = win.header_bar
    hbar._toggle_tag_popup()
    QApplication.processEvents()

    artifact_dir = os.environ.get("ANTIGRAVITY_ARTIFACT_DIR", r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449")
    pix = hbar.tag_popup.grab()
    pix.save(os.path.join(artifact_dir, "test_tag_popup_widget.png"))

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
    capture_popup()
