"""アプリのフォルダの場所。

ソースから動かすときはこのリポジトリのルート、PyInstaller で固めた実行ファイルでは exe と同じフォルダを返す。
catalog.db・settings.ini・error.log・cover_extractor.dll は、このフォルダに置く。
"""

import os
import sys


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
