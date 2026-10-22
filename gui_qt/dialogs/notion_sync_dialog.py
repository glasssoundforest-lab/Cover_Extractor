"""Notion書架同期・プログレスダイアログ (gui_qt/dialogs/notion_sync_dialog.py)

設定されたNotion APIトークンおよびデータベースへ、
収蔵シナリオ情報を非同期バックグラウンドで自動同期・アップロードします。
"""

import os
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QMessageBox,
)

from ..theme import Theme
from ..components.ornate import OrnateFrame, OrnateDivider, make_fleur_pixmap
import app_settings
import notion_sync
from app_settings import Settings


class NotionSyncWorker(QThread):
    """Notion APIを用いたバックグラウンド同期ワーカー"""
    progress = Signal(int, int, str)      # current, total, item_title
    finished_all = Signal(int, int, str)  # success_count, fail_count, error_msg
    request_diff_resolution = Signal(dict, dict, object)  # current_dict, notion_dict, (queue, item_id)

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db_path = getattr(db, "db_path", "catalog.db")
        self.has_diff_receiver = False
        # 自動同調では比較画面を出さず、手元と Notion が食い違う本は保留する（次回の手動同調で確認できる）
        self.defer_conflicts = False
        self.imported_count = 0  # Notion から取り込んだ（手元を更新した）冊数
        self.pushed_count = 0    # Notion へ送った冊数
        self.deferred_count = 0  # 食い違いのため保留した冊数

    def run(self):
        from core.database import Database
        worker_db = Database(self.db_path)

        settings = Settings(app_settings.SETTINGS_FILE)
        token = settings.get_secret("notion", "token") or ""
        db_url_or_id = (
            settings.get("notion", "database_id", "")
            or settings.get("notion", "database_url", "")
            or ""
        ).strip()

        if not token or not db_url_or_id:
            self.finished_all.emit(
                0,
                0,
                "NotionのAPIトークンまたはデータベースIDが設定されていません。\n右上のメニューの「設定」からNotion設定を保存してください。",
            )
            return

        try:
            db_id = notion_sync.database_id_from_url(db_url_or_id)
            client = notion_sync.NotionClient(
                token, request_interval=app_settings.get_api_interval()
            )
            _title, sources = client.data_sources(db_id)
            data_source_id = sources[0][0] if sources else db_id
            schema = client.schema(data_source_id)

            # マッピングの取得（保存済み設定 + 自動推測フォールバック）
            mapping = dict(settings.get_json("notion", "mapping", {}) or {})
            for key, _, _, _ in notion_sync.FIELDS:
                col = settings.get("notion_mapping", key, "")
                if col:
                    mapping[key] = col

            guessed = notion_sync.guess_mapping(schema)
            for key, col in guessed.items():
                if not mapping.get(key) or mapping.get(key) not in schema:
                    mapping[key] = col

            problem = notion_sync.check_mapping(schema, mapping, require_file_path=False)
            if problem:
                self.finished_all.emit(0, 0, f"列マッピングに不備があります:\n{problem}\n設定画面をご確認ください。")
                return

            limit_val = app_settings.get_notion_import_limit()
            import_limit = None if limit_val == 0 else limit_val

            # 前回の同調でどの更新日時まで読み込んだか。分かっていれば、それ以降に更新されたページだけを取得する
            watermark_key = f"notion_watermark:{data_source_id}"
            watermark = worker_db.get_sync_state(watermark_key)
            pages = client.query_all(
                data_source_id,
                filter=notion_sync.edited_since_filter(watermark) if watermark else None,
                sorts=notion_sync.OLDEST_EDIT_FIRST,
            )
        except Exception as e:
            self.finished_all.emit(0, 0, f"Notionへの接続に失敗しました:\n{e}")
            return

        success = 0
        fail = 0
        imported_page_ids = set()
        fresh_page_ids = set()       # 今回 Notion の内容を手元へ取り込んだページ
        needs_push_page_ids = set()
        # 取得したが今回は反映していないページ（保留・失敗・件数上限）。Notion 側の変更を上書きしないよう書き戻さない
        unsettled_page_ids = {p.get("id") for p in pages if p.get("id")}
        new_watermark = None
        watermark_blocked = False

        # 同期前のローカル状態をスナップショット（ローカルで表紙や項目が更新された既存ページを検知するため）
        pre_local_by_pid = {
            it["notion_page_id"]: it
            for it in worker_db.items_for_notion()
            if it.get("notion_page_id")
        }

        # 1. Notion からページを読み込み、シナリオ名・表紙・タグ等を切り分けて DB に登録
        total_remote = len(pages)
        for idx, page in enumerate(pages):
            if self.isInterruptionRequested():
                break
            # 取り込み件数の上限（実際に手元へ取り込んだ冊数で数える。残りは次回の同調で続きから取り込む）
            if import_limit is not None and self.imported_count >= import_limit:
                break

            page_id = page.get("id") or f"notion-page-{idx}"
            notion_edit_time = page.get("last_edited_time") or ""
            vals = notion_sync.page_values(page, mapping, schema)
            title = vals.get("title") or "無題のシナリオ"
            self.progress.emit(idx + 1, max(1, total_remote), title)

            settled = True  # このページを反映し終えたか（保留・失敗なら False）
            try:
                # 既存レコードの探索（page_id一致、file_path一致、または同一タイトル）
                existing = worker_db.find_existing_item_for_notion(
                    page_id=page_id,
                    title=title,
                    file_path=vals.get("file_path"),
                )

                # 同一更新日時の場合はスキップ
                if (
                    existing
                    and existing.get("notion_page_id") == page_id
                    and existing.get("notion_last_edited_time")
                    and existing.get("notion_last_edited_time") == notion_edit_time
                ):
                    imported_page_ids.add(page_id)
                    unsettled_page_ids.discard(page_id)
                    success += 1
                    continue

                cover_url = notion_sync.page_cover_url(page)
                pre_it = pre_local_by_pid.get(page_id) or (
                    existing if existing and existing.get("notion_page_id") == page_id else None
                )
                local_thumb = pre_it.get("thumbnail") if pre_it else (existing.get("thumbnail") if existing else None)
                local_cover_hash = notion_sync.compute_cover_hash(local_thumb)
                local_cover_changed = bool(
                    pre_it and local_thumb and local_cover_hash != pre_it.get("notion_cover_hash")
                )

                thumb_bytes = None
                if cover_url and not local_cover_changed:
                    try:
                        thumb_bytes = client.download(cover_url)
                    except Exception as ce:
                        print(f"[NotionSync] Cover download error for {title}: {ce}")

                if pre_it:
                    # ローカルで表紙が変更されている場合、またはNotion側で空の項目がローカルにある場合はNotionへ書き戻す対象にする
                    if local_cover_changed or (local_thumb and not cover_url):
                        needs_push_page_ids.add(page_id)
                    for k, col in mapping.items():
                        if col and pre_it.get(k) and not vals.get(k):
                            needs_push_page_ids.add(page_id)

                # 手元に同じデータがある（既存レコードあり）かつ差分がある場合は詳細画面（新旧比較選択）を開く
                if existing:
                    curr_dict = {
                        "title": existing.get("title", ""),
                        "author": existing.get("author", ""),
                        "system": existing.get("system_name", ""),
                        "players": existing.get("players_text", ""),
                        "duration": existing.get("duration_text", ""),
                        "overview": existing.get("overview", ""),
                        "synopsis": existing.get("synopsis", ""),
                        "tags": existing.get("tags", []),
                        "thumbnail_bytes": existing.get("thumbnail"),
                    }
                    notion_dict = {
                        "title": vals.get("title", ""),
                        "author": vals.get("author", ""),
                        "system": vals.get("system_name", ""),
                        "players": vals.get("players_text", ""),
                        "duration": vals.get("duration_text", ""),
                        "overview": vals.get("overview", ""),
                        "synopsis": vals.get("synopsis", ""),
                        "tags": vals.get("tags", []),
                        "image_bytes": thumb_bytes,
                    }

                    # 差分の有無を検証
                    has_diff = False
                    for k in ["title", "author", "system", "players", "duration", "overview", "synopsis"]:
                        if (curr_dict.get(k) or "").strip() != (notion_dict.get(k) or "").strip():
                            has_diff = True
                            break
                    if not has_diff and set(curr_dict.get("tags") or []) != set(notion_dict.get("tags") or []):
                        has_diff = True
                    if not has_diff and thumb_bytes and thumb_bytes != curr_dict.get("thumbnail_bytes"):
                        has_diff = True

                    if has_diff and self.defer_conflicts:
                        self.deferred_count += 1
                        settled = False
                        continue

                    if has_diff and getattr(self, "has_diff_receiver", False):
                        import queue
                        res_q = queue.Queue()
                        self.request_diff_resolution.emit(curr_dict, notion_dict, (res_q, existing["id"]))
                        # 比較画面の回答を待つ（中断されたら、この本は変更せずに飛ばす）
                        resolution = {"action": "skip"}
                        while not self.isInterruptionRequested():
                            try:
                                resolution = res_q.get(timeout=0.5)
                                break
                            except queue.Empty:
                                pass

                        action = resolution.get("action")
                        if action == "apply":
                            edited_in_detail = resolution.get("edited_in_detail", False)
                            if edited_in_detail:
                                worker_db.set_notion_link(existing["id"], page_id)
                                with worker_db.conn:
                                    worker_db.conn.execute(
                                        "UPDATE items SET notion_last_edited_time = ? WHERE id = ?;",
                                        (notion_edit_time, existing["id"]),
                                    )
                            else:
                                selected_fields = resolution.get("selected_fields", set())
                                update_vals = dict(vals)
                                field_map = {
                                    "title": "title",
                                    "author": "author",
                                    "system": "system_name",
                                    "players": "players_text",
                                    "duration": "duration_text",
                                    "overview": "overview",
                                    "synopsis": "synopsis",
                                }
                                # 比較画面でその場編集された値を適用
                                for f_key, edited in (resolution.get("edited_values") or {}).items():
                                    if edited and f_key in field_map:
                                        update_vals[field_map[f_key]] = edited
                                    elif edited and f_key == "tags":
                                        update_vals["tags"] = edited
                                for f_key, val_key in field_map.items():
                                    if f_key not in selected_fields:
                                        update_vals[val_key] = existing.get(val_key)
                                if "tags" not in selected_fields:
                                    update_vals["tags"] = existing.get("tags")

                                final_thumb = (
                                    thumb_bytes if "cover" in selected_fields else existing.get("thumbnail")
                                )
                                worker_db.save_or_update_from_notion(
                                    page_id,
                                    update_vals,
                                    thumbnail_bytes=final_thumb,
                                    last_edited_time=notion_edit_time,
                                )
                            # 一部だけ採用・その場編集した場合は手元と Notion が食い違うため、
                            # 「取り込んだばかり」扱いにせず、送った内容との比較で書き戻すかを決める
                            imported_page_ids.add(page_id)
                            unsettled_page_ids.discard(page_id)
                            self.imported_count += 1
                            success += 1
                            continue
                        else:
                            # スキップ選択された場合（次回の同調でもう一度確認する）
                            imported_page_ids.add(page_id)
                            settled = False
                            success += 1
                            continue

                worker_db.save_or_update_from_notion(
                    page_id,
                    vals,
                    thumbnail_bytes=thumb_bytes,
                    last_edited_time=notion_edit_time,
                )
                imported_page_ids.add(page_id)
                fresh_page_ids.add(page_id)
                unsettled_page_ids.discard(page_id)
                self.imported_count += 1
                success += 1
            except Exception as e:
                print(f"[NotionSync] Error importing page {title}: {e}")
                settled = False
                fail += 1
            finally:
                # 更新日時の古い順に処理しているため、保留・失敗したページより前までを「読み込み済み」とする
                if not settled:
                    watermark_blocked = True
                elif not watermark_blocked and notion_edit_time:
                    new_watermark = notion_edit_time

        if new_watermark and (not watermark or new_watermark > watermark):
            worker_db.set_sync_state(watermark_key, new_watermark)

        # 2. ローカル DB にある未同期アイテム（およびローカル変更がある既存アイテム）を Notion テーブル構造に合わせて書き出し
        #    前回 Notion へ送った内容（または Notion と一致を確認した内容）から変わっていないものは送らない
        local_targets = []
        for it in worker_db.items_for_notion():
            page_id = it.get("notion_page_id")
            export_it = dict(it)
            if str(export_it.get("file_path") or "").startswith("notion://"):
                export_it["file_path"] = ""
            props_hash = notion_sync.properties_hash(notion_sync.build_properties(export_it, mapping, schema))
            cover_changed = bool(
                it.get("thumbnail")
                and notion_sync.compute_cover_hash(it.get("thumbnail")) != it.get("notion_cover_hash")
            )
            if page_id in unsettled_page_ids:
                continue
            if not page_id or page_id in needs_push_page_ids:
                local_targets.append((it, export_it, props_hash))
            elif page_id in fresh_page_ids:
                # 今回 Notion から取り込んだばかりで、手元と Notion が一致している
                worker_db.set_notion_sync_state(it["id"], props_hash)
            elif props_hash != it.get("notion_sync_hash") or (cover_changed and page_id not in imported_page_ids):
                local_targets.append((it, export_it, props_hash))
        total_all = total_remote + len(local_targets)

        for idx, (it, export_it, props_hash) in enumerate(local_targets):
            if self.isInterruptionRequested():
                break

            title = it.get("title") or "無題"
            self.progress.emit(total_remote + idx + 1, max(1, total_all), title)

            try:
                page_id = it.get("notion_page_id")
                thumb_bytes = it.get("thumbnail")
                new_cover_hash = notion_sync.compute_cover_hash(thumb_bytes)
                old_cover_hash = it.get("notion_cover_hash")

                cover_upload_id = None
                if thumb_bytes and (not page_id or new_cover_hash != old_cover_hash):
                    try:
                        cover_upload_id = client.upload_file(
                            thumb_bytes, filename="cover.jpg", content_type="image/jpeg"
                        )
                    except Exception as ce:
                        print(f"[NotionSync] Cover upload error for {title}: {ce}")

                props = notion_sync.build_properties(
                    export_it, mapping, schema, cover_upload_id=cover_upload_id
                )

                if page_id:
                    updated = client.update_page(page_id, properties=props, cover_upload_id=cover_upload_id)
                    if cover_upload_id and new_cover_hash:
                        worker_db.set_notion_link(it["id"], page_id, cover_hash=new_cover_hash)
                    if page_id not in imported_page_ids:
                        success += 1
                    self.pushed_count += 1
                else:
                    updated = client.create_page(data_source_id, props, cover_upload_id=cover_upload_id)
                    new_pid = updated.get("id")
                    if new_pid:
                        worker_db.set_notion_link(
                            it["id"],
                            new_pid,
                            cover_hash=new_cover_hash if cover_upload_id else old_cover_hash,
                        )
                    success += 1
                    self.pushed_count += 1
                # 送った内容と、送った結果の Notion 側の更新日時を記録する
                # （次回の同期で、自分で書き込んだページを「Notion 側で更新された」と取り違えて読み直さないため）
                worker_db.set_notion_sync_state(it["id"], props_hash, (updated or {}).get("last_edited_time"))
            except Exception as e:
                print(f"[NotionSync] Error syncing item {title}: {e}")
                fail += 1

        client.close()
        self.finished_all.emit(success, fail, "")


def resolve_notion_diff(parent, db, current_dict, notion_dict, queue_and_id):
    """Notionと手元データで同一または更新がある場合の比較選択ダイアログを表示し、結果を同調処理へ返す"""
    res_q, item_id = queue_and_id
    from .web_info_diff_dialog import WebInfoComparisonDialog

    dlg = WebInfoComparisonDialog(
        current_dict,
        notion_dict,
        parent=parent,
        source_name="Notion",
        db=db,
        item_id=item_id,
    )
    if dlg.exec() == QDialog.Accepted:
        res_q.put({
            "action": "apply",
            "selected_fields": dlg.get_selected_fields(),
            "edited_values": dlg.get_edited_values(),
            "edited_in_detail": getattr(dlg, "edited_in_detail", False),
        })
    else:
        res_q.put({"action": "skip"})


class NotionSyncDialog(QDialog):
    """西洋アンティーク調のNotion同期プログレスダイアログ"""
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.success_count = 0
        self.fail_count = 0
        self.error_message = ""

        self.setWindowTitle("Notion書架との同調")
        self.setFixedSize(480, 220)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setStyleSheet(Theme.get_application_stylesheet())

        self._init_ui()
        self._start_worker()

    def _init_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        self.frame = OrnateFrame(self, bracket_size=16, bg_color="#14100c")
        outer_layout.addWidget(self.frame)

        layout = QVBoxLayout(self.frame)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # 見出し
        head_layout = QHBoxLayout()
        fleur = QLabel()
        fleur.setPixmap(make_fleur_pixmap(16, Theme.BRASS_LIGHT))
        head_layout.addWidget(fleur)

        head_title = QLabel("Notion書架と同調中...")
        head_title.setStyleSheet(f"""
            color: {Theme.BRASS_LIGHT};
            font-size: 14px;
            font-weight: bold;
            font-family: {Theme.FONT_SERIF};
        """)
        head_layout.addWidget(head_title)
        head_layout.addStretch()
        layout.addLayout(head_layout)

        layout.addWidget(OrnateDivider(self, height=8))

        # 状態表示
        self.status_label = QLabel("Notion APIに接続しています...")
        self.status_label.setStyleSheet("color: #dcd0bd; font-size: 12px; font-family: serif;")
        layout.addWidget(self.status_label)

        # プログレスバー
        self.pbar = QProgressBar()
        self.pbar.setRange(0, 100)
        self.pbar.setValue(0)
        self.pbar.setFixedHeight(18)
        self.pbar.setTextVisible(False)
        self.pbar.setStyleSheet(f"""
            QProgressBar {{
                background-color: #1a1511;
                border: 1px solid {Theme.BRASS_BASE};
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #8c703e, stop:1 #d4b26f);
                border-radius: 1px;
            }}
        """)
        layout.addWidget(self.pbar)

        # 下部（件数表示＆キャンセルボタン）
        bottom_layout = QHBoxLayout()
        self.count_label = QLabel("接続確認中...")
        self.count_label.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 11px;")
        bottom_layout.addWidget(self.count_label)
        bottom_layout.addStretch()

        self.cancel_btn = QPushButton("✕  中断")
        self.cancel_btn.setFixedSize(80, 28)
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #1e1713;
                color: {Theme.TEXT_MUTED};
                border: 1px solid #4a3a2a;
                border-radius: 2px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: #2b211a;
                color: #ffffff;
            }}
        """)
        self.cancel_btn.clicked.connect(self._on_cancel)
        bottom_layout.addWidget(self.cancel_btn)
        layout.addLayout(bottom_layout)

    def _start_worker(self):
        self.worker = NotionSyncWorker(self.db, self)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_all.connect(self._on_finished)
        self.worker.request_diff_resolution.connect(self._on_request_diff_resolution)
        self.worker.has_diff_receiver = True
        self.worker.start()

    def _on_request_diff_resolution(self, current_dict, notion_dict, queue_and_id):
        resolve_notion_diff(self, self.db, current_dict, notion_dict, queue_and_id)

    def _on_progress(self, current, total, title):
        self.pbar.setMaximum(total)
        self.pbar.setValue(current)
        self.status_label.setText(f"転送中: 『{title}』")
        self.count_label.setText(f"{current} / {total} 冊")

    def _on_cancel(self):
        if self.worker.isRunning():
            self.worker.requestInterruption()
            self.status_label.setText("同調を中断しています...")
            self.cancel_btn.setEnabled(False)

    def _on_finished(self, success, fail, error_msg):
        self.success_count = success
        self.fail_count = fail
        self.error_message = error_msg
        if hasattr(self, "worker") and self.worker.isRunning():
            self.worker.wait(1000)
        self.accept()

    def closeEvent(self, event):
        if hasattr(self, "worker") and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait(2000)
        super().closeEvent(event)
