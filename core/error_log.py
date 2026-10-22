"""エラーログ（error.log）への書き出し (core/error_log.py)

エラーが起きた日時・そのとき行っていた作業・エラーの内容と詳細（どこで起きたか）を、
アプリのフォルダの error.log に追記する。画面を使わないので、別スレッドの処理からも呼べる。
"""

import os
import threading
import traceback
from datetime import datetime

from core.paths import app_dir  # noqa: E402

ROOT_DIR = app_dir()
# テストでは環境変数で別の場所に書き出す（アプリのフォルダの error.log を汚さないため）
LOG_PATH = os.environ.get("GRIMOIRE_ERROR_LOG") or os.path.join(ROOT_DIR, "error.log")
MAX_LOG_BYTES = 2 * 1024 * 1024  # これを超えたら error.old.log に回して新しく書き始める

_lock = threading.Lock()


def exception_detail(exc):
    """例外の種類・内容と、どこで起きたか（トレースバック）を文字列にする"""
    if exc is None:
        return ""
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).rstrip()


def build_entry(operation, message, detail="", when=None):
    """ログ 1 件分の文章（ポップアップの詳細欄にも同じものを出す）"""
    when = when or datetime.now()
    lines = [
        f"発生日時: {when:%Y-%m-%d %H:%M:%S}",
        f"作業内容: {operation or '（不明）'}",
        f"エラー内容: {message or '（不明）'}",
    ]
    if detail:
        lines += ["詳細:", detail.rstrip()]
    return "\n".join(lines)


def write_entry(entry):
    """組み立て済みの 1 件を error.log に追記する（書けなくてもアプリは止めない）"""
    try:
        with _lock:
            if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > MAX_LOG_BYTES:
                os.replace(LOG_PATH, os.path.splitext(LOG_PATH)[0] + ".old.log")
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write("=" * 60 + "\n" + entry + "\n\n")
        return True
    except OSError:
        return False


def log_error(operation, message, exc=None, detail=""):
    """エラーを 1 件 error.log に書き出し、書き出した文章を返す"""
    detail = detail or exception_detail(exc)
    if not message and exc is not None:
        message = str(exc) or type(exc).__name__
    entry = build_entry(operation, message, detail)
    write_entry(entry)
    return entry
