"""PySide6 版 魔導書架 (main_qt.py)

西洋古書・グリモワール調 TRPG シナリオライブラリ管理アプリケーション
"""

import sys
import os

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))  # 実行ファイル版は exe のあるフォルダ
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# プロジェクトルートを追加
sys.path.insert(0, BASE_DIR)

# catalog.db・settings.ini・cover_extractor.dll はこのフォルダからの相対パスで扱っているため、
# どこから起動しても（ショートカットやエディタの実行ボタン等）このフォルダを作業フォルダにする
os.chdir(BASE_DIR)

from core import error_log  # noqa: E402  (標準ライブラリだけで動くので、起動の失敗も記録できる)


def main():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    from gui_qt import MainWindow, Theme
    from gui_qt.error_dialog import install_excepthook

    # 高DPIスケーリングの有効化
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("魔導書架")
    app.setStyleSheet(Theme.get_application_stylesheet())
    # 想定外のエラーも、詳細をポップアップで表示して error.log に書き出す
    install_excepthook()

    window = MainWindow(db_path="catalog.db")
    window.show()

    return app.exec()


def _report_startup_error(exc):
    """起動に失敗したことを error.log に書き、画面にも出す（ウィンドウが出ないまま黙って終わらないように）"""
    entry = error_log.log_error("アプリの起動", "起動中にエラーが発生しました", exc=exc)
    print(entry, file=sys.stderr)
    try:
        from PySide6.QtWidgets import QApplication
        from gui_qt.error_dialog import ErrorDialog

        app = QApplication.instance() or QApplication(sys.argv)
        ErrorDialog("魔導書架 - 起動エラー", f"起動中にエラーが発生しました: {exc}", "アプリの起動", entry).exec()
    except Exception:
        # 画面の部品自体が読み込めない場合は、最低限のメッセージだけ出す
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox

            app = QApplication.instance() or QApplication(sys.argv)
            box = QMessageBox(QMessageBox.Critical, "魔導書架 - 起動エラー",
                              f"起動中にエラーが発生しました。\n詳細は次のファイルに記録しました:\n{error_log.LOG_PATH}")
            box.setDetailedText(entry)
            box.exec()
        except Exception:
            pass


if __name__ == "__main__":
    try:
        code = main()
    except Exception as e:
        _report_startup_error(e)
        code = 1
    sys.exit(code)
