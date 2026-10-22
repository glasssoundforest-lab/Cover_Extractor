"""テスト一式（python -m unittest tests.test_xxx で実行する）

テスト中に起きるエラーは、アプリのフォルダの error.log ではなく一時フォルダのログへ書き出す。
設定（settings.ini）も、実際のものではなく一時フォルダの別ファイルを使う（ウィンドウの大きさなどを書き換えないため）。
"""

import os
import tempfile

os.environ.setdefault("GRIMOIRE_ERROR_LOG", os.path.join(tempfile.gettempdir(), "grimoire_test_error.log"))
os.environ.setdefault("GRIMOIRE_SETTINGS_FILE", os.path.join(tempfile.gettempdir(), f"grimoire_test_settings_{os.getpid()}.ini"))
