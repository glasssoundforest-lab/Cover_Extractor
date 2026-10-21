"""表紙のバックグラウンド読み込み (gui_qt/components/cover_loader.py)

書架のカードは表紙なしで先に並べ、表紙は別スレッドで DB から読み・縮小・角丸加工してから届ける。
縮小・切り抜きまで済ませた表紙は DB の cover_cache に保存し、次回以降はそれを読むだけで済ませる。
画面に見えているカードから順に読み込むことで、起動直後や絞り込み直後でも画面が固まらない。
"""

import sqlite3
import threading
from collections import OrderedDict

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtGui import QImage

from .scenario_card import COVER_CACHE_VERSION, decode_cover, encode_cover, finish_cover, render_cover_base


class _CoverJob(QRunnable):
    """待ち行列が空になるまで表紙を作り続ける（1度に1つだけ動かす）"""

    # 加工済み表紙を DB に書き込む頻度（この件数ごと、または待ち行列が空になったときにまとめて確定する）
    COMMIT_EVERY = 16

    def __init__(self, loader):
        super().__init__()
        self.loader = loader

    def run(self):
        conn = None
        try:
            conn = sqlite3.connect(self.loader.db_path, timeout=10.0)
            # キャッシュ表は Database の初期化で作られる。ない場合（古い形式の DB を直接開いた等）はキャッシュを使わない
            self.use_cache = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'cover_cache';"
            ).fetchone() is not None
            unsaved = 0
            while True:
                job = self.loader._next_job()
                if job is None:
                    break
                item_id, mode, key = job
                image, conflict, to_store = self._load(conn, item_id, mode)
                try:
                    self.loader.loaded.emit(item_id, mode, key, image if image is not None else QImage(), conflict)
                except RuntimeError:
                    return  # 書架（受け取り側）が既に破棄された
                if to_store is not None and self.use_cache:
                    unsaved += self._store(conn, item_id, mode, conflict, *to_store)
                    if unsaved >= self.COMMIT_EVERY:
                        unsaved = self._commit(conn)
            self._commit(conn)
        except Exception as e:  # noqa: BLE001
            print(f"[CoverLoader] {e}")
        finally:
            if conn is not None:
                conn.close()
            self.loader._job_finished()

    def _load(self, conn, item_id, mode):
        """(表示用画像, 同系色衝突, キャッシュに保存するもの (加工済み画像, 元画像) または None) を返す"""
        try:
            row = self.use_cache and conn.execute(
                "SELECT image, conflict FROM cover_cache WHERE item_id = ? AND mode = ? AND version = ?;",
                (item_id, mode, COVER_CACHE_VERSION),
            ).fetchone()
            if row:
                base = decode_cover(row[0])
                if base is not None:
                    return finish_cover(base, mode), bool(row[1]), None
        except sqlite3.Error:
            pass  # キャッシュ表がない・読めない場合は元画像から作る

        try:
            row = conn.execute("SELECT thumbnail FROM items WHERE id = ?;", (item_id,)).fetchone()
            if not row or not row[0]:
                return None, False, None
            base, conflict = render_cover_base(row[0], mode)
            if base is None:
                return None, False, None
            return finish_cover(base, mode), conflict, (base, row[0])
        except Exception as e:  # noqa: BLE001 - 1件の失敗で他の表紙を止めない
            print(f"[CoverLoader] item {item_id}: {e}")
            return None, False, None

    @staticmethod
    def _store(conn, item_id, mode, conflict, base, source):
        """加工済み表紙をキャッシュに書く。加工中に元画像が差し替わっていたら書かない。書いた件数を返す。"""
        data = encode_cover(base)
        if not data:
            return 0
        try:
            cur = conn.execute(
                """INSERT OR REPLACE INTO cover_cache (item_id, mode, version, image, conflict)
                   SELECT ?, ?, ?, ?, ? WHERE EXISTS (SELECT 1 FROM items WHERE id = ? AND thumbnail = ?);""",
                (item_id, mode, COVER_CACHE_VERSION, data, int(conflict), item_id, source),
            )
            return cur.rowcount
        except sqlite3.Error as e:
            print(f"[CoverLoader] cache item {item_id}: {e}")
            return 0

    @staticmethod
    def _commit(conn):
        try:
            conn.commit()
        except sqlite3.Error as e:
            print(f"[CoverLoader] cache commit: {e}")
        return 0


class CoverLoader(QObject):
    """表紙の読み込み要求を受け付け、出来上がったものを loaded で知らせる"""
    loaded = Signal(int, str, object, QImage, bool)  # item_id, size_mode, thumb_key, image, color_conflict

    def __init__(self, db_path, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self._lock = threading.Lock()
        self._pending = OrderedDict()  # (item_id, mode) -> thumb_key
        self._running = False
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)

    def request(self, jobs):
        """jobs: [(item_id, size_mode, thumb_key), ...] を優先順に渡す。既存の待ちより先に処理する。"""
        with self._lock:
            ordered = OrderedDict()
            for item_id, mode, key in jobs:
                ordered[(item_id, mode)] = key
            for k, v in self._pending.items():
                if k not in ordered:
                    ordered[k] = v
            self._pending = ordered
            if not self._pending or self._running:
                return
            self._running = True
        self._pool.start(_CoverJob(self))

    def cancel_all(self):
        with self._lock:
            self._pending.clear()

    def wait(self, msecs=-1):
        """待ち行列の処理が終わるまで待つ（テスト・終了処理用）"""
        return self._pool.waitForDone(msecs)

    def _next_job(self):
        with self._lock:
            if not self._pending:
                return None
            (item_id, mode), key = self._pending.popitem(last=False)
            return item_id, mode, key

    def _job_finished(self):
        restart = False
        with self._lock:
            self._running = False
            if self._pending:
                self._running = True
                restart = True
        if restart:
            self._pool.start(_CoverJob(self))
