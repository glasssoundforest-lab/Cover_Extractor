"""詳細編集画面で、グローバルタグとローカルタグの領域を分けて、それぞれ別ウィンドウの一覧から編集できることの検証"""

import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog

from core.database import Database
from gui_qt.components.ornate import PillTag
from gui_qt.dialogs.item_detail_dialog import ItemDetailDialog, MultiTagEditDialog


def pill_names(layout):
    names = []
    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item.widget() and isinstance(item.widget(), PillTag):
            names.append(item.widget().text)
        elif item.layout():
            for j in range(item.layout().count()):
                w = item.layout().itemAt(j).widget()
                if isinstance(w, PillTag):
                    names.append(w.text)
    return names


class TestTagAreas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = Database(os.path.join(self.tmp, "t.db"))
        self.id = self.db.save_item("a.pdf", "題", "", "", "", "", "", None)
        self.db.add_tags_to_item(self.id, ["CoC", "未通過", "ホラー"])
        self.dlg = ItemDetailDialog(self.id, self.db)
        self.dlg.show()
        self.dlg._toggle_edit_mode()
        QApplication.processEvents()

    def tearDown(self):
        self.dlg.close()
        self.db.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_01_areas_are_separate(self):
        self.assertEqual(sorted(pill_names(self.dlg.global_flow_layout)), ["CoC", "未通過"])
        self.assertEqual(pill_names(self.dlg.tags_flow_layout), ["ホラー"])
        self.assertTrue(self.dlg.edit_global_tags_btn.isVisible())
        self.assertTrue(self.dlg.edit_tags_btn.isVisible())
        self.dlg._toggle_edit_mode()
        self.assertFalse(self.dlg.edit_global_tags_btn.isVisible())
        self.assertFalse(self.dlg.edit_tags_btn.isVisible())

    def test_02_dialog_lists_only_its_kind(self):
        g = MultiTagEditDialog(self.id, self.db, self.dlg, is_global=True)
        names = {cb.text() for cb in g.checkboxes.values()}
        self.assertIn("マダミス", names)
        self.assertNotIn("ホラー", names)
        self.assertEqual({cb.text() for cb in g.checkboxes.values() if cb.isChecked()}, {"CoC", "未通過"})
        self.assertTrue(g.new_tag_in.isHidden())
        loc = MultiTagEditDialog(self.id, self.db, self.dlg)
        self.assertEqual({cb.text() for cb in loc.checkboxes.values()}, {"ホラー"})
        self.assertFalse(loc.new_tag_in.isHidden())

    def _pick(self, is_global, names):
        class Fake:
            def __init__(s, item_id, db, parent=None, is_global=False):
                s.ids = [t[0] for t in (db.get_global_tags() if is_global else db.get_local_tags()) if t[1] in names]

            def exec(s):
                return QDialog.Accepted

            def get_selected_tag_ids(s):
                return s.ids

        with patch("gui_qt.dialogs.item_detail_dialog.MultiTagEditDialog", Fake):
            (self.dlg._on_edit_global_tags if is_global else self.dlg._on_edit_tags)()

    def test_03_edit_global_keeps_local(self):
        self._pick(True, ["マダミス", "GM可"])
        self.assertEqual(sorted(pill_names(self.dlg.global_flow_layout)), ["GM可", "マダミス"])
        self.assertEqual(pill_names(self.dlg.tags_flow_layout), ["ホラー"])
        self.assertEqual({t[1] for t in self.db.get_item_tags(self.id)}, {"マダミス", "GM可", "ホラー"})

    def test_04_edit_local_keeps_global(self):
        self.db.add_tag("山岳", is_global=0)
        self._pick(False, ["山岳"])
        self.assertEqual(pill_names(self.dlg.tags_flow_layout), ["山岳"])
        self.assertEqual(sorted(pill_names(self.dlg.global_flow_layout)), ["CoC", "未通過"])

    def test_05_empty_areas(self):
        self.db.set_item_tags(self.id, [])
        self.dlg._render_tags()
        self.assertEqual(pill_names(self.dlg.global_flow_layout), [])
        self.assertEqual(self.dlg.tags_box.text(), "タグなし")


if __name__ == "__main__":
    unittest.main()
