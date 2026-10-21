"""書架の仮想化・表紙キャッシュの検証テスト (tests/test_bookshelf_virtualization.py)

1. 冊数が多くても、カードは画面付近の分だけ作られ、重ならずに並ぶこと
2. スクロールすると、その位置のカードが作られること
3. 表紙キャッシュが保存され、直接加工した表紙と画素単位で一致すること
4. 表紙の差し替え・削除でキャッシュが破棄されること
5. 作り直す前に依頼した表紙の読み込み結果を、新しいカードが受け取らないこと
6. マウスが乗ったまま隠れたカードを再利用しても、ホバー表示が残らないこと
"""

import os
import sys
import shutil
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from core.database import Database
from gui_qt.main_window import MainWindow
from gui_qt.components.scenario_card import decode_cover, finish_cover, render_cover

ITEM_COUNT = 120


def make_cover(index):
    img = QImage(300, 430, QImage.Format_RGB32)
    img.fill(QColor.fromHsv((index * 37) % 360, 160, 120 + index % 100))
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def pump(seconds=0.2):
    """別スレッドからの通知を受け取れるよう、GIL を手放しながらイベントを処理する"""
    end = time.time() + seconds
    while time.time() < end:
        QApplication.processEvents()
        time.sleep(0.01)


class TestBookshelfVirtualization(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
        cls.tmp_dir = tempfile.mkdtemp()
        cls.db_path = os.path.join(cls.tmp_dir, "test_virtualization.db")
        cls.db = Database(cls.db_path)
        cls.ids = [
            cls.db.save_item(f"C:/scenarios/book_{i:03d}.pdf", f"書物 {i:03d}", "クトゥルフ神話TRPG",
                             "1〜4人", "3時間", "", "", make_cover(i))
            for i in range(ITEM_COUNT)
        ]
        cls.win = MainWindow(db_path=cls.db_path)
        cls.win.resize(1260, 820)
        cls.win.show()
        pump()
        cls.bookshelf = cls.win.bookshelf
        cls.bookshelf.wait_for_covers(20000)

    @classmethod
    def tearDownClass(cls):
        cls.win.close()
        cls.db.conn.close()
        shutil.rmtree(cls.tmp_dir, ignore_errors=True)

    def _visible_cards(self):
        return [c for c in self.bookshelf.cards if c.isVisible()]

    def test_01_only_nearby_cards_are_created(self):
        self.assertEqual(len(self.bookshelf.current_items), ITEM_COUNT)
        cards = self._visible_cards()
        self.assertGreater(len(cards), 0)
        self.assertLess(len(cards), ITEM_COUNT // 2)
        rects = [c.geometry() for c in cards]
        for i, a in enumerate(rects):
            for b in rects[:i]:
                self.assertFalse(a.intersects(b), "カードが重なっている")

    def test_02_scrolling_materializes_cards(self):
        sb = self.bookshelf.scroll.verticalScrollBar()
        sb.setValue(sb.maximum())
        pump()
        shown_ids = {c.item_id for c in self._visible_cards()}
        last_id = self.bookshelf.current_items[-1][0]
        self.assertIn(last_id, shown_ids)
        sb.setValue(0)
        pump()
        self.assertIn(self.bookshelf.current_items[0][0], {c.item_id for c in self._visible_cards()})

    def test_03_cover_cache_matches_direct_render(self):
        self.bookshelf.wait_for_covers(20000)
        rows = self.db.conn.execute(
            "SELECT item_id, mode, image, conflict FROM cover_cache WHERE mode = ?;", (self.bookshelf.view_mode,)
        ).fetchall()
        self.assertGreater(len(rows), 0)
        for item_id, mode, data, conflict in rows[:5]:
            thumb = self.db.conn.execute("SELECT thumbnail FROM items WHERE id = ?;", (item_id,)).fetchone()[0]
            direct, direct_conflict = render_cover(thumb, mode)
            cached = finish_cover(decode_cover(data), mode)
            self.assertEqual(bool(conflict), direct_conflict)
            self.assertEqual(direct.convertToFormat(QImage.Format_ARGB32), cached.convertToFormat(QImage.Format_ARGB32))

    def test_04_cache_invalidated_on_cover_change_and_delete(self):
        self.bookshelf.wait_for_covers(20000)
        item_id = self.db.conn.execute("SELECT item_id FROM cover_cache LIMIT 1;").fetchone()[0]
        count = lambda: self.db.conn.execute(  # noqa: E731
            "SELECT COUNT(*) FROM cover_cache WHERE item_id = ?;", (item_id,)).fetchone()[0]
        self.db.update_item_meta(item_id, "改題された書物", "クトゥルフ神話TRPG", "1〜4人", "3時間")
        self.assertGreater(count(), 0, "表紙以外の更新でキャッシュが消えた")
        self.db.update_item_cover(item_id, make_cover(999))
        self.assertEqual(count(), 0)

        victim = self.ids[-1]
        self.db.conn.execute(
            "INSERT OR REPLACE INTO cover_cache (item_id, mode, version, image, conflict) VALUES (?, 'medium', 1, x'00', 0);",
            (victim,))
        self.db.conn.commit()
        self.db.delete_item(victim)
        self.assertEqual(self.db.conn.execute(
            "SELECT COUNT(*) FROM cover_cache WHERE item_id = ?;", (victim,)).fetchone()[0], 0)
        self.win.reload_data()
        pump()

    def test_05_stale_cover_result_is_ignored_after_invalidate(self):
        self.bookshelf.scroll.verticalScrollBar().setValue(0)
        pump()
        self.bookshelf.wait_for_covers(20000)
        card = self._visible_cards()[0]
        item_id, old_key = card.item_id, card.thumb_key
        self.assertIsNotNone(old_key)

        self.bookshelf.invalidate_items([item_id])
        if self.bookshelf.cover_loader:
            self.bookshelf.cover_loader.cancel_all()
        self.bookshelf.display_items(self.bookshelf.current_items, self.bookshelf.all_gtags)
        pump(0.05)
        new_card = next(c for c in self.bookshelf.cards if c.item_id == item_id)
        self.assertIsNot(new_card, card)
        self.assertNotEqual(new_card.thumb_key, old_key)

        # 作り直す前に依頼した結果（古い識別子付き）が遅れて届いても反映されないこと
        stale = QImage(10, 10, QImage.Format_ARGB32)
        stale.fill(QColor("#ff00ff"))
        if not new_card.cover_loaded:
            self.bookshelf._on_cover_loaded(item_id, self.bookshelf.view_mode, old_key, stale, False)
            self.assertFalse(new_card.cover_loaded)
        self.bookshelf.wait_for_covers(20000)
        self.assertTrue(new_card.cover_loaded)

    def test_06_hover_state_reset_when_card_hidden(self):
        self.bookshelf.scroll.verticalScrollBar().setValue(0)
        pump()
        card = self._visible_cards()[0]
        card.is_hovered = True
        card._update_appearance()
        self.assertEqual(card.property("active"), "true")

        self.win._on_search_changed("該当する書物なし")
        self.win._filter_and_display()
        pump()
        self.assertFalse(card.isVisible())
        self.assertFalse(card.is_hovered)
        self.assertEqual(card.property("active"), "false")

        self.win._on_search_changed("")
        pump()


if __name__ == "__main__":
    unittest.main()
