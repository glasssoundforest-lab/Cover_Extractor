"""書架データのバックアップ＆復元モジュール (core/backup_manager.py)

catalog.db、settings.ini、メタデータ情報をひとつの安全なZipアーカイブとして
エクスポート（書き出し）およびインポート（復元）します。
"""

import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime


class BackupManager:
    BACKUP_VERSION = "1.0"
    INFO_FILENAME = "grimoire_backup_info.json"

    @classmethod
    def get_stats(cls, db_path: str) -> dict:
        """指定DBの統計情報（シナリオ数、タグ数、セッション履歴数）を取得"""
        stats = {"item_count": 0, "tag_count": 0, "playlog_count": 0}
        if not os.path.exists(db_path):
            return stats
        try:
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM items;")
            stats["item_count"] = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM tags;")
            stats["tag_count"] = c.fetchone()[0]
            try:
                c.execute("SELECT COUNT(*) FROM play_logs;")
                stats["playlog_count"] = c.fetchone()[0]
            except sqlite3.OperationalError:
                pass
            conn.close()
        except Exception:
            pass
        return stats

    @staticmethod
    def _drop_cover_cache(snap_db):
        """スナップショットから表紙キャッシュを除く（元画像から作り直せるため、バックアップを小さく保つ）"""
        if not os.path.exists(snap_db):
            return
        conn = sqlite3.connect(snap_db)
        try:
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'cover_cache';").fetchone():
                if conn.execute("SELECT 1 FROM cover_cache LIMIT 1;").fetchone():
                    conn.execute("DELETE FROM cover_cache;")
                    conn.commit()
                    conn.execute("VACUUM;")
        except sqlite3.Error as e:
            print(f"[Backup] cover cache cleanup skipped: {e}")
        finally:
            conn.close()

    @classmethod
    def create_backup(cls,zip_dest_path: str, db_path: str, settings_path: str = "settings.ini") -> dict:
        """書架データ（DB、設定ファイル、メタデータ）をZipアーカイブに書き出す"""
        stats = cls.get_stats(db_path)
        info = {
            "version": cls.BACKUP_VERSION,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "stats": stats,
            "has_settings": os.path.exists(settings_path),
        }

        temp_dir = tempfile.mkdtemp()
        try:
            # 1. 整合性を保ったDBスナップショットの取得（VACUUM INTO または オンラインバックアップ）
            snap_db = os.path.join(temp_dir, "catalog.db")
            if os.path.exists(db_path):
                src_conn = sqlite3.connect(db_path)
                try:
                    # SQLite 3.27+ VACUUM INTO
                    src_conn.execute(f"VACUUM INTO '{snap_db}';")
                except Exception:
                    # フォールバック: backup API
                    dst_conn = sqlite3.connect(snap_db)
                    src_conn.backup(dst_conn)
                    dst_conn.close()
                finally:
                    src_conn.close()
                cls._drop_cover_cache(snap_db)
            # 2. メタデータ情報ファイル
            info_file = os.path.join(temp_dir, cls.INFO_FILENAME)
            with open(info_file, "w", encoding="utf-8") as f:
                json.dump(info, f, ensure_ascii=False, indent=2)

            # 3. Zipアーカイブの構築
            # 既存ファイルがある場合は上書き用の一時ファイルを作成してからリプレイス
            tmp_zip = zip_dest_path + ".tmp"
            with zipfile.ZipFile(tmp_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.write(info_file, cls.INFO_FILENAME)
                if os.path.exists(snap_db):
                    zf.write(snap_db, "catalog.db")
                if os.path.exists(settings_path):
                    zf.write(settings_path, "settings.ini")

            if os.path.exists(zip_dest_path):
                os.remove(zip_dest_path)
            os.rename(tmp_zip, zip_dest_path)

            return info
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    @classmethod
    def inspect_backup(cls, zip_path: str) -> dict:
        """バックアップZipを検査し、メタ情報と整合性を返す"""
        if not os.path.exists(zip_path):
            raise FileNotFoundError(f"バックアップファイルが見つかりません: {zip_path}")

        if not zipfile.is_zipfile(zip_path):
            raise ValueError("有効なZip形式のバックアップファイルではありません。")

        with zipfile.ZipFile(zip_path, "r") as zf:
            namelist = zf.namelist()
            if cls.INFO_FILENAME not in namelist:
                raise ValueError("魔導書架のバックアップ識別情報が含まれていません。")

            info_data = zf.read(cls.INFO_FILENAME).decode("utf-8")
            info = json.loads(info_data)
            info["contains_db"] = "catalog.db" in namelist
            info["contains_settings"] = "settings.ini" in namelist
            return info

    @classmethod
    def restore_backup(
        cls,
        zip_path: str,
        db_path: str,
        settings_path: str = "settings.ini",
        restore_settings: bool = True,
    ) -> dict:
        """バックアップZipからDBおよび設定ファイルを復元する（安全のための事前自動退避付き）"""
        info = cls.inspect_backup(zip_path)

        temp_dir = tempfile.mkdtemp()
        backup_bak_dir = tempfile.mkdtemp()
        try:
            # 0. 現在のファイルを安全のために一時退避
            db_bak = None
            if os.path.exists(db_path):
                db_bak = os.path.join(backup_bak_dir, "catalog.db.bak")
                shutil.copy2(db_path, db_bak)

            settings_bak = None
            if os.path.exists(settings_path):
                settings_bak = os.path.join(backup_bak_dir, "settings.ini.bak")
                shutil.copy2(settings_path, settings_bak)

            # 1. Zipを一時ディレクトリに解凍
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(temp_dir)

            extracted_db = os.path.join(temp_dir, "catalog.db")
            extracted_settings = os.path.join(temp_dir, "settings.ini")

            # 2. DBの復元
            if os.path.exists(extracted_db):
                # 破損していないか簡易チェック
                test_conn = sqlite3.connect(extracted_db)
                test_conn.execute("PRAGMA integrity_check;")
                test_conn.close()

                dest_db_folder = os.path.dirname(os.path.abspath(db_path))
                os.makedirs(dest_db_folder, exist_ok=True)
                shutil.copy2(extracted_db, db_path)

            # 3. 設定ファイルの復元
            if restore_settings and os.path.exists(extracted_settings):
                dest_st_folder = os.path.dirname(os.path.abspath(settings_path))
                os.makedirs(dest_st_folder, exist_ok=True)
                shutil.copy2(extracted_settings, settings_path)

            return info
        except Exception as e:
            # エラー発生時は退避ファイルから自動ロールバック
            if db_bak and os.path.exists(db_bak):
                shutil.copy2(db_bak, db_path)
            if settings_bak and os.path.exists(settings_bak):
                shutil.copy2(settings_bak, settings_path)
            raise RuntimeError(f"復元処理中にエラーが発生したため、変更をロールバックしました:\n{e}") from e
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
            shutil.rmtree(backup_bak_dir, ignore_errors=True)
