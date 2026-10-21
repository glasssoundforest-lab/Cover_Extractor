"""サイドバーの部分更新と描画キャッシュの検証テスト (tests/test_sidebar_and_paint_cache.py)

1. タグ一覧が同じなら作り直さず、作り直しても選択中のタグの表示が保たれること
2. 一覧から消えたタグは選択からも外れ、絞り込みの変更が通知されること
3. システム分類の顔ぶれが同じなら、行を作り直さず件数だけ更新されること
4. 文字の影のキャッシュが Qt 標準の影と同じ見た目で、文字が変わると描き直されること
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QGraphicsDropShadowEffect, QLabel, QWidget

from gui_qt.components.sidebar import Sidebar
from gui_qt.components.scenario_card import _CachedDropShadow

TAGS = [("CoC", "#1b5e20"), ("未通過", "#1565c0"), ("未設定", "#607d8b")]


def _max_channel_diff(a, b):
    a = a.convertToFormat(QImage.Format_ARGB32)
    b = b.convertToFormat(QImage.Format_ARGB32)
    if a.size() != b.size():
        return 255
    return max((abs(x - y) for x, y in zip(bytes(a.constBits()), bytes(b.constBits()))), default=0)


class TestSidebarIncrementalUpdate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        self.sidebar = Sidebar()
        self.emitted = []
        self.sidebar.tags_changed.connect(self.emitted.append)

    def tearDown(self):
        self.sidebar.deleteLater()

    def test_01_same_tags_keep_widgets_and_selection(self):
        self.sidebar.set_tags(TAGS)
        pill = self.sidebar.tag_widgets["CoC"]
        QTest.mouseClick(pill, Qt.LeftButton, Qt.NoModifier, QPoint(5, 5))
        self.assertEqual(self.sidebar.selected_tags, {"CoC"})

        self.sidebar.set_tags(list(TAGS))
        self.assertIs(self.sidebar.tag_widgets["CoC"], pill)
        self.assertTrue(pill.is_checked)

        # 一覧が変わって作り直しても、選択中の表示は保たれる
        self.sidebar.set_tags(TAGS[:2] + [("GM可", "#b3882a")] + TAGS[2:])
        self.assertIsNot(self.sidebar.tag_widgets["CoC"], pill)
        self.assertTrue(self.sidebar.tag_widgets["CoC"].is_checked)
        self.assertFalse(self.sidebar.tag_widgets["GM可"].is_checked)

    def test_02_removed_tag_is_unselected(self):
        self.sidebar.set_tags(TAGS)
        QTest.mouseClick(self.sidebar.tag_widgets["未通過"], Qt.LeftButton, Qt.NoModifier, QPoint(5, 5))
        self.emitted.clear()
        self.sidebar.set_tags([t for t in TAGS if t[0] != "未通過"])
        self.assertEqual(self.sidebar.selected_tags, set())
        self.assertEqual(self.emitted, [[]])

    def test_03_same_systems_update_counts_only(self):
        self.sidebar.set_systems({"クトゥルフ神話TRPG": 3, "マダミス": 1}, favorite_count=1)
        row = self.sidebar.system_widgets["マダミス"]
        self.sidebar.set_systems({"クトゥルフ神話TRPG": 3, "マダミス": 2}, favorite_count=2)
        self.assertIs(self.sidebar.system_widgets["マダミス"], row)
        self.assertEqual(row.count_label.text(), "2")
        self.assertEqual(self.sidebar.system_widgets["すべて"].count_label.text(), "5")
        self.assertEqual(self.sidebar.fav_button.count_lbl.text(), "2")

        self.sidebar.set_systems({"クトゥルフ神話TRPG": 3, "マダミス": 2, "その他": 1})
        self.assertIn("その他", self.sidebar.system_widgets)
        self.assertEqual(self.sidebar.system_widgets["すべて"].count_label.text(), "6")


class TestCachedDropShadow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def _make(self, effect_cls, text):
        host = QWidget()
        host.resize(220, 60)
        host.setStyleSheet("QWidget { background: #8c703e; } QLabel { background: transparent; color: #d4b26f; }")
        label = QLabel(text, host)
        label.setGeometry(12, 10, 190, 36)
        effect = effect_cls(label)
        effect.setOffset(1, 1)
        effect.setBlurRadius(4)
        effect.setColor(QColor(0, 0, 0, 225))
        label.setGraphicsEffect(effect)
        return host, label

    def test_04_matches_standard_shadow_and_follows_text(self):
        std_host, std_label = self._make(QGraphicsDropShadowEffect, "影付きの書名")
        host, label = self._make(_CachedDropShadow, "影付きの書名")
        self.assertLessEqual(_max_channel_diff(std_host.grab().toImage(), host.grab().toImage()), 1)
        # 2回目以降（キャッシュから描画）も同じ
        self.assertLessEqual(_max_channel_diff(std_host.grab().toImage(), host.grab().toImage()), 1)

        std_label.setText("改題された書名")
        label.setText("改題された書名")
        label.graphicsEffect().setBlurRadius(5)
        std_label.graphicsEffect().setBlurRadius(5)
        self.assertLessEqual(_max_channel_diff(std_host.grab().toImage(), host.grab().toImage()), 1)
        for w in (std_host, host):
            w.deleteLater()


if __name__ == "__main__":
    unittest.main()
