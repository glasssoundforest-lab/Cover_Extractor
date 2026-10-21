"""バックグラウンド実行ヘルパー (gui_qt/async_task.py)

ネットワーク通信などの待ち時間の長い処理を画面スレッドの外で実行し、
完了後の処理（結果の反映・ダイアログ表示）を画面スレッドへ戻して呼び出します。

注意: 別スレッドで実行する関数の中では、画面のウィジェットや画面スレッドで作った
Database（sqlite3 の接続）を触らないこと。DB が必要なら関数の中で Database(db_path) を開く。
"""

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from shiboken6 import isValid

_running = set()  # 実行中タスクの参照保持（完了前にガベージコレクトされないように）


class _Relay(QObject):
    done = Signal(object)
    failed = Signal(object)


class _Task(QRunnable):
    def __init__(self, fn, relay):
        super().__init__()
        self.fn = fn
        self.relay = relay
        self.setAutoDelete(False)

    def run(self):
        try:
            result = self.fn()
        except Exception as e:  # noqa: BLE001 - 例外は画面スレッドへ渡して表示する
            signal, value = self.relay.failed, e
        else:
            signal, value = self.relay.done, result
        try:
            signal.emit(value)
        except RuntimeError:
            pass  # アプリ終了後に処理が終わった場合（受け取り側は既に破棄済み）


def run_async(fn, on_done, on_error=None, owner=None):
    """fn() を別スレッドで実行し、結果を on_done(result) / 例外を on_error(exc) に渡す。

    コールバックは画面スレッドで呼ばれる。owner（ウィジェット）が完了前に破棄された場合は呼ばない。
    """
    relay = _Relay()
    task = _Task(fn, relay)
    entry = (relay, task)
    _running.add(entry)

    def _finish(callback, value):
        _running.discard(entry)
        if owner is not None and not isValid(owner):
            return
        if callback is not None:
            callback(value)

    relay.done.connect(lambda result: _finish(on_done, result))
    relay.failed.connect(lambda exc: _finish(on_error, exc))
    QThreadPool.globalInstance().start(task)
    return task
