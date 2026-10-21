"""URLからシナリオを取り込むダイアログ (gui_qt/dialogs/add_scenario_url_dialog.py)

BOOTH, TALTO, 各種Webサイト、または NotionのページURLを入力・貼り付けして、
自動的にシナリオ情報（タイトル、作者、システム、人数、時間、概要、あらすじ、表紙画像、タグ）
を取得し、書架に新規シナリオとして登録します。
"""

import os
import re
import urllib.parse
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QColor
from PySide6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QMessageBox,
    QApplication,
    QFrame,
)

from ..theme import Theme
from ..components.ornate import OrnateFrame, OrnateDivider
from ..components.ornate_title_bar import OrnateTitleBar
import app_settings
from ..async_task import run_async


class AddScenarioUrlDialog(QDialog):
    """URLからシナリオを取り込むアンティーク調ダイアログ"""
    scenario_imported = Signal(int)  # 登録された item_id

    def __init__(self, db, initial_url="", parent=None):
        super().__init__(parent)
        self.db = db
        self.added_item_id = None
        self.imported_item_id = None
        self.added_title = ""

        self.setWindowTitle("異稿 - 網羅 - URLからシナリオ取り込み")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.resize(620, 360)
        self.setStyleSheet(Theme.get_application_stylesheet())

        self._init_ui(initial_url)

    @property
    def result_item_id(self):
        return self.imported_item_id or self.added_item_id

    def _init_ui(self, initial_url):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        self.root_frame = OrnateFrame(self, bracket_size=16, bg_color="#120e0b")
        outer_layout.addWidget(self.root_frame)

        root_layout = QVBoxLayout(self.root_frame)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 1. タイトルバー
        self.title_bar = OrnateTitleBar("異稿 - 網羅 - URLからシナリオ取り込み", parent=self, show_close=True)
        root_layout.addWidget(self.title_bar)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(28, 20, 28, 20)
        content_layout.setSpacing(14)
        root_layout.addWidget(content, 1)

        # 2. 案内文
        guide_lbl = QLabel(
            "WEBサイト（BOOTH・TALTO等）や NotionのページURLを入力してください。\n"
            "タイトル、作者、システム、人数、時間、概要、あらすじ、表紙画像を自動解析して書架に登録します。"
        )
        guide_lbl.setStyleSheet(f"color: #d8c2aa; font-size: 12px; font-family: {Theme.FONT_SERIF}; line-height: 1.4;")
        guide_lbl.setWordWrap(True)
        content_layout.addWidget(guide_lbl)

        # 3. URL入力エリア
        input_box = QVBoxLayout()
        input_box.setSpacing(6)

        url_title_box = QHBoxLayout()
        url_caption = QLabel("❖ 取り込み対象URL:")
        url_caption.setStyleSheet(f"color: {Theme.BRASS_LIGHT}; font-weight: bold; font-size: 13px; font-family: {Theme.FONT_SERIF};")
        url_title_box.addWidget(url_caption)

        paste_btn = QPushButton("📋 貼り付け")
        paste_btn.setFixedSize(80, 22)
        paste_btn.setCursor(Qt.PointingHandCursor)
        paste_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #261d15;
                color: {Theme.BRASS_LIGHT};
                border: 1px solid {Theme.BRASS_BASE};
                border-radius: 11px;
                font-size: 10px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #3b2c1d;
                border: 1px solid {Theme.BRASS_LIGHT};
                color: #ffffff;
            }}
        """)
        paste_btn.clicked.connect(self._on_paste_clipboard)
        url_title_box.addWidget(paste_btn)
        url_title_box.addStretch()

        input_box.addLayout(url_title_box)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://booth.pm/ja/items/... または NotionページURL")
        self.url_input.setFixedHeight(34)
        self.url_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: #191410;
                color: #ffffff;
                border: 1px solid {Theme.BRASS_BASE};
                border-radius: 3px;
                padding: 4px 8px;
                font-size: 13px;
                font-family: {Theme.FONT_SERIF};
            }}
            QLineEdit:focus {{
                border: 1px solid {Theme.BRASS_LIGHT};
                background-color: #221a14;
            }}
        """)
        self.url_input.textChanged.connect(self._on_text_changed)
        input_box.addWidget(self.url_input)

        # 判定プレビューラベル
        self.preview_lbl = QLabel("")
        self.preview_lbl.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 11px;")
        input_box.addWidget(self.preview_lbl)

        content_layout.addLayout(input_box)

        # 初期値またはクリップボードからの自動設定
        target_init = initial_url.strip()
        if not target_init:
            clip_text = QApplication.clipboard().text().strip()
            if clip_text.startswith("http://") or clip_text.startswith("https://") or clip_text.startswith("notion://"):
                target_init = clip_text

        if target_init:
            self.url_input.setText(target_init)
            self._update_preview(target_init)

        content_layout.addStretch()

        # 4. 下部区切り線＆ボタンエリア
        content_layout.addWidget(OrnateDivider())

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 4, 0, 0)
        btn_row.setSpacing(12)

        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet(f"color: {Theme.BRASS_LIGHT}; font-size: 12px; font-weight: bold;")
        btn_row.addWidget(self.status_lbl)
        btn_row.addStretch()

        cancel_btn = QPushButton("✕ 取消")
        cancel_btn.setFixedSize(90, 32)
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #261d15;
                color: {Theme.TEXT_MUTED};
                border: 1px solid #4a3a2a;
                border-radius: 2px;
                font-size: 12px;
                font-family: {Theme.FONT_SERIF};
            }}
            QPushButton:hover {{
                background-color: #3b2c1d;
                color: #ffffff;
                border: 1px solid {Theme.BRASS_BASE};
            }}
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        self.import_btn = QPushButton("🌐  取り込み開始")
        self.import_btn.setFixedSize(140, 32)
        self.import_btn.setCursor(Qt.PointingHandCursor)
        self.import_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #2a1f14;
                color: {Theme.BRASS_LIGHT};
                border: 1px solid {Theme.BRASS_LIGHT};
                border-radius: 2px;
                font-weight: bold;
                font-size: 12px;
                font-family: {Theme.FONT_SERIF};
            }}
            QPushButton:hover {{
                background-color: #443220;
                color: #ffffff;
                border: 1px solid #e2c07d;
            }}
            QPushButton:disabled {{
                background-color: #1a1512;
                color: #665a4c;
                border: 1px solid #332820;
            }}
        """)
        self.import_btn.clicked.connect(self._on_import_clicked)
        btn_row.addWidget(self.import_btn)

        content_layout.addLayout(btn_row)

    def _on_paste_clipboard(self):
        text = QApplication.clipboard().text().strip()
        if text:
            self.url_input.setText(text)

    def _on_text_changed(self, text):
        self._update_preview(text.strip())

    def _update_preview(self, url):
        if not url:
            self.preview_lbl.setText("")
            return
        if "notion.so" in url.lower() or "notion.site" in url.lower() or url.lower().startswith("notion://"):
            self.preview_lbl.setText("📓 Notion ページとして認識されました（Notion API 経由で取得）")
            self.preview_lbl.setStyleSheet(f"color: {Theme.BRASS_LIGHT}; font-size: 11px;")
        elif url.lower().startswith("http://") or url.lower().startswith("https://"):
            try:
                host = urllib.parse.urlparse(url).netloc
                self.preview_lbl.setText(f"🌐 Web サイト（{host}）として認識されました（自動解析で取得）")
                self.preview_lbl.setStyleSheet("color: #69db7c; font-size: 11px;")
            except Exception:
                self.preview_lbl.setText("🌐 Web サイトとして認識されました")
                self.preview_lbl.setStyleSheet("color: #69db7c; font-size: 11px;")
        else:
            self.preview_lbl.setText("⚠ 有効な URL（http:// または https://）を入力してください")
            self.preview_lbl.setStyleSheet("color: #e74c3c; font-size: 11px;")

    def _on_import_clicked(self):
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "警告", "取り込み対象のURLを入力してください。")
            return

        # 不正文字・制御文字チェック
        if any(c in url for c in "\x00\r\n\t") or any(ord(c) < 32 for c in url):
            QMessageBox.warning(self, "警告", "URLに不正な制御文字が含まれています。")
            return

        lower = url.lower()
        if "notion.so" in lower or "notion.site" in lower or lower.startswith("notion://"):
            fetch, finish = self._fetch_notion, self._import_from_notion
        elif lower.startswith("http://") or lower.startswith("https://"):
            fetch, finish = self._fetch_web, self._import_from_web
        else:
            QMessageBox.warning(self, "エラー", "対応していないURL形式です。\nhttp:// または https:// で始まるURLを入力してください。")
            return

        # 通信は別スレッドで行い、その間も画面を操作できるようにする（取消も可能）
        self.import_btn.setEnabled(False)
        self.status_lbl.setText("⏳ 情報を取得中...")
        run_async(
            lambda: fetch(url),
            lambda fetched: self._on_fetch_finished(url, finish, fetched),
            self._on_fetch_failed,
            owner=self,
        )

    def _on_fetch_finished(self, url, finish, fetched):
        if not self.isVisible():
            return  # 取得中に取消された
        try:
            item_id, title = finish(url, fetched)
            if item_id is None:
                # 比較画面でキャンセルまたは選択項目なし
                return

            self.added_item_id = item_id
            self.imported_item_id = item_id
            self.added_title = title
            self.scenario_imported.emit(item_id)
            self.accept()
        except Exception as e:
            QMessageBox.warning(self, "取り込み失敗", f"シナリオ情報の取得に失敗しました:\n{e}")
        finally:
            self.import_btn.setEnabled(True)
            self.status_lbl.setText("")

    def _on_fetch_failed(self, error):
        self.import_btn.setEnabled(True)
        self.status_lbl.setText("")
        if self.isVisible():
            QMessageBox.warning(self, "取り込み失敗", f"シナリオ情報の取得に失敗しました:\n{error}")

    @staticmethod
    def _fetch_notion(url):
        """（別スレッドでも呼べる）Notion ページと表紙画像を取得する。DB や画面は触らない。"""
        token = app_settings.get_settings().get_secret("notion", "token")
        if not token:
            raise ValueError(
                "Notion API のトークンが設定されていません。\n"
                "環境設定の「Notion連携・環境」タブからトークンを設定してください。"
            )

        clean_url = url.split("?", 1)[0].split("#", 1)[0]
        m = re.findall(
            r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b|\b[0-9a-fA-F]{32}\b",
            clean_url,
        )
        if not m:
            raise ValueError("URLからNotionのページIDを読み取れませんでした。\nNotionページのURLを正しくコピーしてください。")

        raw_id = m[-1].replace("-", "").lower()
        page_id = f"{raw_id[0:8]}-{raw_id[8:12]}-{raw_id[12:16]}-{raw_id[16:20]}-{raw_id[20:]}"

        from notion_sync import NotionClient, page_cover_url

        client = NotionClient(token)
        page = client.request("GET", f"/v1/pages/{page_id}")
        if not page or not isinstance(page, dict):
            raise ValueError("Notionからページ情報を取得できませんでした。")

        cover_url = page_cover_url(page)
        thumb_bytes = None
        if cover_url:
            try:
                thumb_bytes = client.download(cover_url)
            except Exception as e:
                print(f"[AddScenarioUrl] Cover download failed: {e}")
        return {"page_id": page_id, "page": page, "thumb_bytes": thumb_bytes}

    def _import_from_notion(self, url, fetched=None):
        """Notion URLからの取り込み（比較画面による確認・採否選択対応）

        fetched: _fetch_notion() の結果。省略時はここで取得する。
        """
        from notion_sync import guess_mapping, page_values, page_notion_url
        from .web_info_diff_dialog import WebInfoComparisonDialog

        if fetched is None:
            fetched = self._fetch_notion(url)
        page_id = fetched["page_id"]
        page = fetched["page"]
        thumb_bytes = fetched["thumb_bytes"]

        props = page.get("properties") or {}
        schema = {pname: pval.get("type") for pname, pval in props.items() if isinstance(pval, dict)}

        mapping = guess_mapping(schema)
        vals = page_values(page, mapping, schema)

        vals["notion_url"] = page_notion_url(page)
        last_edited = page.get("last_edited_time") or ""

        # 既存アイテムの探索
        title = vals.get("title") or "無題のシナリオ"
        existing_item = self.db.find_existing_item_for_notion(page_id, title)
        existing_item_id = existing_item["id"] if existing_item else None
        current_data = self.db.get_item_detail_dict(existing_item_id) if existing_item_id else {}

        # 比較ダイアログ用データ整形
        curr_comp = dict(current_data) if current_data else {}
        if "system_name" in curr_comp and "system" not in curr_comp:
            curr_comp["system"] = curr_comp["system_name"]

        notion_comp = dict(vals)
        if thumb_bytes and "thumbnail_bytes" not in notion_comp:
            notion_comp["thumbnail_bytes"] = thumb_bytes
        if "system_name" in notion_comp and "system" not in notion_comp:
            notion_comp["system"] = notion_comp["system_name"]

        diff_dlg = WebInfoComparisonDialog(
            current_data=curr_comp,
            web_data=notion_comp,
            parent=self,
            source_name="Notion情報",
            db=self.db,
            item_id=existing_item_id,
        )
        if diff_dlg.exec() != QDialog.Accepted:
            return None, None

        if getattr(diff_dlg, "edited_in_detail", False):
            it = self.db.get_item(existing_item_id)
            return existing_item_id, it[2] if it else title

        selected_fields = diff_dlg.get_selected_fields()
        if not selected_fields:
            QMessageBox.information(self, "案内", "反映対象として選択された項目はありませんでした。")
            return None, None

        # 比較画面でその場編集された値を反映元データへ適用
        vals = dict(vals)
        notion_key_map = {
            "title": "title", "author": "author", "system": "system_name",
            "players": "players_text", "duration": "duration_text",
            "overview": "overview", "synopsis": "synopsis", "tags": "tags",
        }
        for f_key, edited in diff_dlg.get_edited_values().items():
            if edited and f_key in notion_key_map:
                vals[notion_key_map[f_key]] = edited

        # 選択された項目のみ反映するように vals をフィルタリング
        filtered_vals = {}
        for k in ("title", "title_kana", "file_path", "source_url", "notion_url"):
            if k in vals:
                filtered_vals[k] = vals[k]
        if "system" in selected_fields and "system_name" in vals:
            filtered_vals["system_name"] = vals["system_name"]
        if "players" in selected_fields and "players_text" in vals:
            filtered_vals["players_text"] = vals["players_text"]
        if "duration" in selected_fields and "duration_text" in vals:
            filtered_vals["duration_text"] = vals["duration_text"]
        if "overview" in selected_fields and "overview" in vals:
            filtered_vals["overview"] = vals["overview"]
        if "synopsis" in selected_fields and "synopsis" in vals:
            filtered_vals["synopsis"] = vals["synopsis"]
        if "author" in selected_fields and "author" in vals:
            filtered_vals["author"] = vals["author"]
        if "tags" in selected_fields and "tags" in vals:
            filtered_vals["tags"] = vals["tags"]

        chosen_thumb = thumb_bytes if "cover" in selected_fields else None

        item_id = self.db.save_or_update_from_notion(
            page_id, filtered_vals, thumbnail_bytes=chosen_thumb, last_edited_time=last_edited
        )
        return item_id, vals.get("title") or "無題のシナリオ"

    @staticmethod
    def _fetch_web(url):
        """（別スレッドでも呼べる）Web ページから情報と表紙画像を取得する。DB や画面は触らない。"""
        from core.web_extractor import WebScenarioExtractor
        return WebScenarioExtractor.extract_from_url(url, fetch_image=True)

    def _import_from_web(self, url, data=None):
        """Webサイト URL（BOOTH, TALTO等）からの取り込み（比較画面による確認・採否選択対応）

        data: _fetch_web() の結果。省略時はここで取得する。
        """
        from .web_info_diff_dialog import WebInfoComparisonDialog

        if data is None:
            data = self._fetch_web(url)
        title = data.get("title") or "無題のシナリオ"

        # 既存アイテム探索
        existing_row = self.db.find_existing_item_for_web(url, title)
        existing_item_id = existing_row[0] if existing_row else None
        current_data = self.db.get_item_detail_dict(existing_item_id) if existing_item_id else {}

        # 比較ダイアログ用データ整形
        curr_comp = dict(current_data) if current_data else {}
        if "system_name" in curr_comp and "system" not in curr_comp:
            curr_comp["system"] = curr_comp["system_name"]

        web_comp = dict(data)
        if "image_bytes" in web_comp and "thumbnail_bytes" not in web_comp:
            web_comp["thumbnail_bytes"] = web_comp["image_bytes"]

        diff_dlg = WebInfoComparisonDialog(
            current_data=curr_comp,
            web_data=web_comp,
            parent=self,
            source_name="Web情報",
            db=self.db,
            item_id=existing_item_id,
        )
        if diff_dlg.exec() != QDialog.Accepted:
            # ユーザーがキャンセル
            return None, None

        if getattr(diff_dlg, "edited_in_detail", False):
            it = self.db.get_item(existing_item_id)
            return existing_item_id, it[2] if it else title

        selected_fields = diff_dlg.get_selected_fields()
        if not selected_fields:
            QMessageBox.information(self, "案内", "反映対象として選択された項目はありませんでした。")
            return None, None

        # 比較画面でその場編集された値を反映
        data = dict(data)
        for f_key, edited in diff_dlg.get_edited_values().items():
            if edited:
                data[f_key] = edited

        item_id, final_title = self.db.save_or_update_from_web(
            url, data, selected_fields=selected_fields, existing_item_id=existing_item_id
        )
        return item_id, final_title
