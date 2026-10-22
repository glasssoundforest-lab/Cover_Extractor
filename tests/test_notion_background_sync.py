"""Notion との通信の軽量化とバックグラウンド同調の検証テスト (tests/test_notion_background_sync.py)

実際の Notion には接続しない（手元の HTTP サーバーと、Notion を模した偽のクライアントを使う）。

1. 接続を使い回し、gzip 圧縮された応答を展開できること
2. 混雑（429）のときは待って再試行し、認証エラー（401）は分かりやすい文で伝えること
3. 同調で、手元で変わっていない本は Notion へ送らないこと（2回目の同調では通信が増えない）
4. 手元で変えた本だけを送り、送った後の Notion 側の更新日時を記録すること
5. 同調中も画面を塞がず、下部のステータスバーに進み具合と結果を表示すること
6. 2回目以降は、前回以降に Notion 側で更新されたページだけを取得すること
7. 取り込み件数の上限があっても、次回の同調で続きから取り込むこと
8. 自動同調では、手元と Notion が食い違う本を上書きせず保留すること
9. 自動同調は初期設定では無効であること
"""

import gzip
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication

import notion_sync
from core.database import Database


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"  # 接続の使い回し（keep-alive）を許す

    def log_message(self, *args):
        pass

    def _reply(self, status, obj, headers=None, compress=False):
        body = json.dumps(obj).encode("utf-8")
        if compress:
            body = gzip.compress(body)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if compress:
            self.send_header("Content-Encoding", "gzip")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        server = self.server
        server.connections.add(id(self.connection))
        server.requests.append(self.path)
        if self.path.startswith("/v1/busy"):
            server.busy_count += 1
            if server.busy_count == 1:
                self._reply(429, {"code": "rate_limited", "message": "slow down"}, {"Retry-After": "0"})
                return
            self._reply(200, {"ok": "after retry"})
        elif self.path.startswith("/v1/unauthorized"):
            self._reply(401, {"code": "unauthorized", "message": "API token is invalid."})
        else:
            gz = "gzip" in (self.headers.get("Accept-Encoding") or "")
            self._reply(200, {"path": self.path, "text": "書架" * 200}, compress=gz)


class TestNotionClientTransport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.server.connections = set()
        cls.server.requests = []
        cls.server.busy_count = 0
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_01_reuses_connection_and_decodes_gzip(self):
        client = notion_sync.NotionClient("secret", api_base=self.base, request_interval=0)
        self.server.connections.clear()
        for i in range(5):
            res = client.request("GET", f"/v1/items/{i}")
            self.assertEqual(res["path"], f"/v1/items/{i}")
            self.assertEqual(res["text"], "書架" * 200)
        client.close()
        self.assertEqual(len(self.server.connections), 1, "リクエストごとに接続し直している")

    def test_02_retry_on_rate_limit_and_describe_auth_error(self):
        client = notion_sync.NotionClient("secret", api_base=self.base, request_interval=0)
        self.assertEqual(client.request("GET", "/v1/busy")["ok"], "after retry")
        with self.assertRaises(notion_sync.NotionError) as cm:
            client.request("GET", "/v1/unauthorized")
        self.assertIn("401", str(cm.exception))
        client.close()

    def test_03_reconnects_after_server_closed_connection(self):
        client = notion_sync.NotionClient("secret", api_base=self.base, request_interval=0)
        client.request("GET", "/v1/a")
        # サーバー側で切れた接続を使い回しても、作り直して成功すること
        for conn in client._conns.values():
            conn.sock.close()
        self.assertEqual(client.request("GET", "/v1/b")["path"], "/v1/b")
        client.close()


SCHEMA = {"名前": "title", "システム": "select", "人数": "rich_text", "概要": "rich_text"}


class FakeNotion:
    """Notion を模した偽のクライアント（呼ばれた書き込みを記録する）"""

    def __init__(self):
        self.pages = {}
        self.calls = []
        self.queries = []
        self.clock = 0

    def _stamp(self):
        self.clock += 1
        return f"2026-10-22T00:{self.clock:02d}:00.000Z"

    def data_sources(self, db_id):
        return "書架", [("ds-1", "")]

    def schema(self, ds):
        return dict(SCHEMA)

    def query_all(self, ds, limit=None, progress=None, filter=None, sorts=None):
        self.queries.append(filter)
        pages = list(self.pages.values())
        if filter:
            since = filter["last_edited_time"]["on_or_after"]
            pages = [p for p in pages if p["last_edited_time"] >= since]
        if sorts:
            pages.sort(key=lambda p: p["last_edited_time"])
        return pages[:limit] if limit else pages

    def edit_in_notion(self, pid, **values):
        """Notion 側でページが編集されたことにする"""
        props = notion_sync.build_properties(values, MAPPING, SCHEMA)
        return self._page(pid, props)

    @staticmethod
    def _as_response(props):
        """送る形式の properties を、Notion の応答と同じ形（type・plain_text 付き）にする"""
        out = {}
        for name, value in props.items():
            ptype = SCHEMA.get(name) or next(iter(value))
            body = value.get(ptype)
            if isinstance(body, list):
                body = [dict(t, plain_text=t.get("text", {}).get("content", "")) for t in body]
            out[name] = {"type": ptype, ptype: body}
        return out

    def _page(self, pid, props):
        page = self.pages.get(pid, {"id": pid, "object": "page", "properties": {}})
        page["properties"].update(self._as_response(props))
        page["last_edited_time"] = self._stamp()
        self.pages[pid] = page
        return page

    def create_page(self, ds, props, cover_upload_id=None):
        self.calls.append(("create", props))
        return self._page(f"page-{len(self.pages) + 1}", props)

    def update_page(self, pid, properties=None, cover_upload_id=None):
        self.calls.append(("update", pid))
        return self._page(pid, properties or {})

    def upload_file(self, data, filename="cover.jpg", content_type="image/jpeg"):
        self.calls.append(("upload", filename))
        return "upload-1"

    def download(self, url):
        return None

    def close(self):
        pass


MAPPING = {"title": "名前", "system_name": "システム", "players_text": "人数", "overview": "概要"}


class _FakeSettings:
    def __init__(self, path):
        pass

    def get_secret(self, section, key):
        return "secret"

    def get(self, section, key, default=None):
        return {("notion", "database_id"): "0123456789abcdef0123456789abcdef"}.get((section, key), default)

    def get_json(self, section, key, default):
        return dict(MAPPING)


class TestNotionSyncTraffic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        from gui_qt.dialogs import notion_sync_dialog as mod

        self.mod = mod
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "sync.db")
        self.db = Database(self.db_path)
        self.ids = [
            self.db.save_item(f"C:/books/{i}.pdf", f"書物{i}", "クトゥルフ神話TRPG", "2人", "3時間", f"概要{i}", "", None)
            for i in range(3)
        ]
        self.fake = FakeNotion()
        self._orig = (mod.Settings, notion_sync.NotionClient, mod.app_settings.get_notion_import_limit)
        mod.Settings = _FakeSettings
        notion_sync.NotionClient = lambda *a, **k: self.fake
        mod.app_settings.get_notion_import_limit = lambda: 0

    def tearDown(self):
        self.mod.Settings, notion_sync.NotionClient, self.mod.app_settings.get_notion_import_limit = self._orig
        self.db.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _sync(self, auto=False):
        worker = self.mod.NotionSyncWorker(self.db)
        worker.defer_conflicts = auto
        result = []
        worker.finished_all.connect(lambda s, f, e: result.append((s, f, e)))
        worker.run()  # 同じスレッドで実行して結果を確かめる
        self.assertEqual(result[-1][2], "", result[-1][2])
        return worker

    def _title(self, item_id):
        return self.db.conn.execute("SELECT title FROM items WHERE id = ?;", (item_id,)).fetchone()[0]

    def test_06_fetches_only_pages_edited_since_last_sync(self):
        self._sync()
        self.assertIsNone(self.fake.queries[-1], "初回は全件を取得する")
        self._sync()  # 作ったページを一度読み込むと、どこまで読み込んだかが記録される
        pid = self.db.get_notion_page_id(self.ids[0])
        self.fake.edit_in_notion(pid, title="Notionで改題", system_name="クトゥルフ神話TRPG", players_text="2人", overview="概要0")
        self.fake.calls.clear()
        worker = self._sync()
        self.assertIsNotNone(self.fake.queries[-1], "2回目以降は更新日時で絞り込んで取得する")
        self.assertEqual(worker.imported_count, 1)
        self.assertEqual(self._title(self.ids[0]), "Notionで改題")
        self.assertEqual(self.fake.calls, [], "取り込んだだけの本を送り返している")

    def test_07_import_limit_continues_next_time(self):
        self.db.conn.execute("DELETE FROM items;")
        self.db.conn.commit()
        for i in range(3):
            self.fake.edit_in_notion(f"remote-{i}", title=f"Notionの書物{i}", system_name="クトゥルフ神話TRPG",
                                     players_text="3人", overview=f"概要{i}")
        self.mod.app_settings.get_notion_import_limit = lambda: 1
        counts = [self._sync().imported_count for _ in range(4)]
        self.assertEqual(counts, [1, 1, 1, 0])
        titles = {r[0] for r in self.db.conn.execute("SELECT title FROM items;")}
        self.assertEqual(titles, {"Notionの書物0", "Notionの書物1", "Notionの書物2"})
        self.assertNotIn("create", [c[0] for c in self.fake.calls], "取り込んだ本を Notion に作り直している")

    def test_08_auto_sync_defers_conflicts(self):
        self._sync()
        pid = self.db.get_notion_page_id(self.ids[2])
        # 手元と Notion の両方で同じ本を書き換える
        self.db.update_item_meta(self.ids[2], "手元で改題", "クトゥルフ神話TRPG", "2人", "3時間")
        self.fake.edit_in_notion(pid, title="Notionで改題", system_name="クトゥルフ神話TRPG", players_text="2人", overview="概要2")
        self.fake.calls.clear()
        for _ in range(2):  # 保留した本は次の同調でも取り直す（読み飛ばさない）
            worker = self._sync(auto=True)
            self.assertEqual(worker.deferred_count, 1)
            self.assertEqual(self._title(self.ids[2]), "手元で改題", "保留すべき本を Notion の内容で上書きした")
            self.assertEqual(self.fake.calls, [], "保留すべき本を Notion へ送って上書きした")

    def test_04_unchanged_items_are_not_sent_again(self):
        self._sync()
        self.assertEqual([c[0] for c in self.fake.calls], ["create"] * 3)

        self.fake.calls.clear()
        self._sync()
        self.assertEqual(self.fake.calls, [], "変わっていない本を Notion へ送り直している")

    def test_04b_import_limit_does_not_cause_resending(self):
        # 取り込み件数の上限で読まなかったページの本も、変わっていなければ送り直さない
        self._sync()
        self.mod.app_settings.get_notion_import_limit = lambda: 1
        self.fake.calls.clear()
        self._sync()
        self.assertEqual(self.fake.calls, [], "上限で読まなかったページを毎回上書きしている")

    def test_05_only_locally_changed_item_is_sent(self):
        self._sync()
        self.fake.calls.clear()
        self.db.update_item_meta(self.ids[1], "改題された書物", "クトゥルフ神話TRPG", "2人", "3時間")
        self._sync()
        pid = self.db.get_notion_page_id(self.ids[1])
        self.assertEqual(self.fake.calls, [("update", pid)])

        # 送った後の Notion 側の更新日時を記録しているため、次の同調では読み直しも送り直しもしない
        stored = self.db.conn.execute(
            "SELECT notion_last_edited_time FROM items WHERE id = ?;", (self.ids[1],)).fetchone()[0]
        self.assertEqual(stored, self.fake.pages[pid]["last_edited_time"])
        self.fake.calls.clear()
        self._sync()
        self.assertEqual(self.fake.calls, [])


class TestBackgroundSyncUi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_09_auto_sync_is_off_by_default(self):
        import app_settings
        from gui_qt.main_window import MainWindow

        tmp = tempfile.mkdtemp()
        orig = (app_settings.SETTINGS_FILE, app_settings._settings_instance)
        app_settings.SETTINGS_FILE = os.path.join(tmp, "settings.ini")
        app_settings._settings_instance = None
        try:
            self.assertEqual(app_settings.get_notion_auto_sync(), (False, 30))
            win = MainWindow(db_path=os.path.join(tmp, "ui.db"))
            self.assertFalse(win._auto_sync_timer.isActive())
            self.assertFalse(win._auto_sync_kickoff.isActive())

            cfg = app_settings.load()
            cfg.update(notion_auto_sync=True, notion_auto_sync_interval=15)
            app_settings.save(cfg)
            win._apply_auto_sync_settings()
            self.assertTrue(win._auto_sync_timer.isActive())
            self.assertEqual(win._auto_sync_timer.interval(), 15 * 60 * 1000)
            win.close()
            win.db.conn.close()
        finally:
            app_settings.SETTINGS_FILE, app_settings._settings_instance = orig
            shutil.rmtree(tmp, ignore_errors=True)

    def test_10_status_bar_shows_progress_without_blocking(self):
        from gui_qt.dialogs import notion_sync_dialog as mod
        from gui_qt.main_window import MainWindow

        tmp = tempfile.mkdtemp()
        started = threading.Event()
        release = threading.Event()

        class SlowWorker(mod.NotionSyncWorker):
            def run(self):
                self.imported_count = 2
                self.progress.emit(1, 2, "書物A")
                started.set()
                while not release.is_set() and not self.isInterruptionRequested():
                    time.sleep(0.01)
                self.finished_all.emit(2, 0, "")

        orig = mod.NotionSyncWorker
        mod.NotionSyncWorker = SlowWorker
        win = MainWindow(db_path=os.path.join(tmp, "ui.db"))
        try:
            win.show()
            win._on_notion_sync_requested()
            self.assertTrue(started.wait(5))
            deadline = time.time() + 2
            while time.time() < deadline and "書物A" not in win.status_bar.sync_label.text():
                QApplication.processEvents()
                time.sleep(0.01)
            # 同調中もモーダルな画面は出ておらず、進み具合がステータスバーに出ている
            self.assertIsNone(QApplication.activeModalWidget())
            self.assertIn("書物A", win.status_bar.sync_label.text())
            self.assertTrue(win.status_bar.sync_cancel_btn.isVisible())

            release.set()
            deadline = time.time() + 5
            while time.time() < deadline and win._notion_worker is not None:
                QApplication.processEvents()
                time.sleep(0.01)
            self.assertIsNone(win._notion_worker)
            self.assertIn("取り込み 2 件", win.status_bar.sync_label.text())
            self.assertFalse(win.status_bar.sync_cancel_btn.isVisible())
        finally:
            release.set()
            mod.NotionSyncWorker = orig
            win.close()
            win.db.conn.close()
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
