"""書架対照録 ― Notion書架との差異・不足分リストアップ照合ダイアログ (gui_qt/dialogs/notion_diff_dialog.py)

手元（ローカルDB）の収蔵データとNotion側のデータを突き合わせ、
お互いに足りていないシナリオや、項目に欠落・差異があるシナリオを一覧表示します。
"""

import os
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QFrame,
    QWidget,
    QProgressBar,
    QMessageBox,
)

from ..theme import Theme
from ..components.ornate import OrnateFrame, OrnateDivider, make_fleur_pixmap
from ..components.ornate_title_bar import OrnateTitleBar
from .web_info_diff_dialog import WebInfoComparisonDialog
from ..async_task import run_async
from ..error_dialog import show_error
from core import error_log
from shiboken6 import isValid
import app_settings
import notion_sync
from app_settings import Settings


class NotionAuditWorker(QThread):
    """Notionとのデータ照合を非同期バックグラウンドで実行するワーカー"""
    progress = Signal(str)
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db_path = getattr(db, "db_path", "catalog.db")

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
            self.error.emit(
                "NotionのAPIトークンまたはデータベースIDが設定されていません。\n"
                "設定画面からNotion連携情報を保存してください。"
            )
            return

        try:
            self.progress.emit("Notion APIに接続しています...")
            db_id = notion_sync.database_id_from_url(db_url_or_id)
            client = notion_sync.NotionClient(
                token, request_interval=app_settings.get_api_interval()
            )
            _title, sources = client.data_sources(db_id)
            data_source_id = sources[0][0] if sources else db_id
            schema = client.schema(data_source_id)

            mapping = dict(settings.get_json("notion", "mapping", {}) or {})
            for key, _, _, _ in notion_sync.FIELDS:
                col = settings.get("notion_mapping", key, "")
                if col:
                    mapping[key] = col

            diff_result = notion_sync.audit_notion_diff(
                worker_db,
                client,
                data_source_id,
                mapping=mapping,
                schema=schema,
                progress_callback=self.progress.emit,
            )

            diff_result["client"] = client
            diff_result["data_source_id"] = data_source_id
            self.finished.emit(diff_result)
        except Exception as e:
            self.error.emit(f"照合に失敗しました:\n{e}\n\n[詳細]\n{error_log.exception_detail(e)}")


class NotionDiffDialog(QDialog):
    """手元データとNotionデータの差異・不足分リストアップ照合ダイアログ"""

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.diff_data = None
        self.client = None
        self.data_source_id = None
        self._busy = False  # 1件ずつの書き出し・取り込みの通信中か

        self.setWindowTitle("書架対照録 ― Notion書架との差異・不足分照合")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.resize(920, 680)
        self.setStyleSheet(Theme.get_application_stylesheet())

        self._init_ui()
        self._start_audit()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.frame = OrnateFrame(self, bracket_size=16, bg_color="#14100c")
        main_layout.addWidget(self.frame)

        layout = QVBoxLayout(self.frame)
        layout.setContentsMargins(0, 0, 0, 16)
        layout.setSpacing(10)

        # タイトルバー
        self.title_bar = OrnateTitleBar(
            "❖ 書架対照録 ― 手元とNotionの相互差異・不足分照合",
            parent=self,
            show_close=True,
        )
        layout.addWidget(self.title_bar)

        # サマリーバナー
        self.summary_box = QFrame()
        self.summary_box.setObjectName("summary_box")
        self.summary_box.setStyleSheet(f"""
            QFrame#summary_box {{
                background-color: #1a140f;
                border: 1px solid #3d2f21;
                border-radius: 4px;
                margin: 0 16px;
            }}
            QFrame#summary_box QLabel {{
                border: none;
                background: transparent;
            }}
        """)
        s_layout = QHBoxLayout(self.summary_box)
        s_layout.setContentsMargins(14, 8, 14, 8)
        s_layout.setSpacing(16)

        self.status_label = QLabel("Notion書架と手元の収蔵録を照合中...")
        self.status_label.setStyleSheet(f"color: {Theme.BRASS_LIGHT}; font-size: 12px; font-weight: bold;")
        s_layout.addWidget(self.status_label, 1)


        self.badge_local_only = QLabel("手元のみ: -")
        self.badge_local_only.setStyleSheet("color: #ff8787; font-size: 11px; font-weight: bold;")
        s_layout.addWidget(self.badge_local_only)

        self.badge_notion_only = QLabel("Notionのみ: -")
        self.badge_notion_only.setStyleSheet("color: #74c0fc; font-size: 11px; font-weight: bold;")
        s_layout.addWidget(self.badge_notion_only)

        self.badge_field_lacking = QLabel("項目不足・差異: -")
        self.badge_field_lacking.setStyleSheet("color: #ffd43b; font-size: 11px; font-weight: bold;")
        s_layout.addWidget(self.badge_field_lacking)

        self.badge_in_sync = QLabel("完全一致: -")
        self.badge_in_sync.setStyleSheet("color: #69db7c; font-size: 11px; font-weight: bold;")
        s_layout.addWidget(self.badge_in_sync)

        layout.addWidget(self.summary_box)

        # プログレスバー（照合中用）
        self.pbar = QProgressBar()
        self.pbar.setRange(0, 0)
        self.pbar.setFixedHeight(6)
        self.pbar.setTextVisible(False)
        self.pbar.setStyleSheet(f"""
            QProgressBar {{
                background-color: #120e0b;
                border: none;
                margin: 0 16px;
            }}
            QProgressBar::chunk {{
                background-color: {Theme.BRASS_LIGHT};
            }}
        """)
        layout.addWidget(self.pbar)

        # タブウィジェット
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid #3d2f21;
                background-color: #120e0b;
                margin: 0 16px;
            }}
            QTabBar::tab {{
                background-color: #1a140f;
                color: {Theme.TEXT_MUTED};
                border: 1px solid #3d2f21;
                border-bottom: none;
                padding: 6px 14px;
                margin-right: 2px;
                font-size: 12px;
                font-family: {Theme.FONT_SERIF};
            }}
            QTabBar::tab:selected {{
                background-color: #241c14;
                color: {Theme.BRASS_LIGHT};
                font-weight: bold;
                border-top: 2px solid {Theme.BRASS_LIGHT};
            }}
            QTabBar::tab:hover:!selected {{
                background-color: #201710;
                color: #e0d0b8;
            }}
        """)

        # タブ1: 手元のみ（Notion未登録）
        self.tab_local_only = self._build_local_only_tab()
        self.tabs.addTab(self.tab_local_only, "📘 手元のみ (Notion未登録)")

        # タブ2: Notionのみ（手元未登録）
        self.tab_notion_only = self._build_notion_only_tab()
        self.tabs.addTab(self.tab_notion_only, "☁️ Notionのみ (手元未登録)")

        # タブ3: 項目不足・差異あり
        self.tab_field_lacking = self._build_field_lacking_tab()
        self.tabs.addTab(self.tab_field_lacking, "⚖️ 項目不足・差異あり")

        layout.addWidget(self.tabs, 1)

        # 下部ボタンバー
        layout.addWidget(OrnateDivider(self, height=8))

        btn_bar = QHBoxLayout()
        btn_bar.setContentsMargins(16, 0, 16, 0)
        btn_bar.setSpacing(10)

        self.btn_recheck = QPushButton("🔄  再照合")
        self.btn_recheck.setFixedHeight(30)
        self.btn_recheck.setCursor(Qt.PointingHandCursor)
        self.btn_recheck.setStyleSheet(f"""
            QPushButton {{
                background-color: #241c14;
                color: {Theme.BRASS_LIGHT};
                border: 1px solid #4a3a2a;
                border-radius: 2px;
                padding: 0 12px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: #382c1f;
                color: #ffffff;
            }}
        """)
        self.btn_recheck.clicked.connect(self._start_audit)
        btn_bar.addWidget(self.btn_recheck)

        self.btn_sync_all = QPushButton("⚡  Notion同期ダイアログを開く...")
        self.btn_sync_all.setFixedHeight(30)
        self.btn_sync_all.setCursor(Qt.PointingHandCursor)
        self.btn_sync_all.setStyleSheet(f"""
            QPushButton {{
                background-color: #2a1a12;
                color: #ffda73;
                border: 1px solid #5a3a2a;
                border-radius: 2px;
                padding: 0 12px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: #3d2418;
                color: #ffffff;
            }}
        """)
        self.btn_sync_all.clicked.connect(self._open_sync_dialog)
        btn_bar.addWidget(self.btn_sync_all)

        btn_bar.addStretch()

        btn_close = QPushButton("閉じる")
        btn_close.setFixedSize(90, 30)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setStyleSheet(f"""
            QPushButton {{
                background-color: #1a1511;
                color: {Theme.TEXT_MUTED};
                border: 1px solid #4a3a2a;
                border-radius: 2px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: #251d16;
                color: #ffffff;
            }}
        """)
        btn_close.clicked.connect(self.accept)
        btn_bar.addWidget(btn_close)

        layout.addLayout(btn_bar)

    def _build_local_only_tab(self):
        """タブ1: 手元のみ（Notion未登録）のUI構築"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # 説明 & アクションバー
        top_bar = QHBoxLayout()
        desc = QLabel("手元の書架にのみ収蔵されており、Notion側にはまだ登録されていないシナリオです。")
        desc.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 11px;")
        top_bar.addWidget(desc, 1)

        self.btn_export_all_local = QPushButton("⚡ すべてNotionへ書き出す")
        self.btn_export_all_local.setFixedHeight(26)
        self.btn_export_all_local.setCursor(Qt.PointingHandCursor)
        self.btn_export_all_local.setStyleSheet(f"""
            QPushButton {{
                background-color: #5c1818;
                color: #f7e7c4;
                border: 1px solid {Theme.BRASS_LIGHT};
                border-radius: 2px;
                padding: 0 10px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #7a2020;
                color: #ffffff;
            }}
        """)
        self.btn_export_all_local.clicked.connect(self._export_all_local_only)
        top_bar.addWidget(self.btn_export_all_local)
        layout.addLayout(top_bar)

        # テーブル
        self.table_local_only = self._create_styled_table(
            ["タイトル", "作者", "システム", "人数 / 時間", "表紙", "操作"]
        )
        self.table_local_only.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table_local_only.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table_local_only.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_local_only.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table_local_only.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table_local_only.horizontalHeader().setSectionResizeMode(5, QHeaderView.Fixed)
        self.table_local_only.setColumnWidth(5, 120)
        layout.addWidget(self.table_local_only)

        return widget

    def _build_notion_only_tab(self):
        """タブ2: Notionのみ（手元未登録）のUI構築"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # 説明 & アクションバー
        top_bar = QHBoxLayout()
        desc = QLabel("Notion側に登録されていますが、手元の書架にはまだ取り込まれていないシナリオです。")
        desc.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 11px;")
        top_bar.addWidget(desc, 1)

        self.btn_import_all_notion = QPushButton("⚡ すべて手元へ取り込む")
        self.btn_import_all_notion.setFixedHeight(26)
        self.btn_import_all_notion.setCursor(Qt.PointingHandCursor)
        self.btn_import_all_notion.setStyleSheet(f"""
            QPushButton {{
                background-color: #1a385c;
                color: #d0e7ff;
                border: 1px solid #4a7ab5;
                border-radius: 2px;
                padding: 0 10px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #234c7d;
                color: #ffffff;
            }}
        """)
        self.btn_import_all_notion.clicked.connect(self._import_all_notion_only)
        top_bar.addWidget(self.btn_import_all_notion)
        layout.addLayout(top_bar)

        # テーブル
        self.table_notion_only = self._create_styled_table(
            ["タイトル", "作者", "タグ", "表紙", "操作"]
        )
        self.table_notion_only.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table_notion_only.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table_notion_only.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_notion_only.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table_notion_only.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self.table_notion_only.setColumnWidth(4, 120)
        layout.addWidget(self.table_notion_only)

        return widget

    def _build_field_lacking_tab(self):
        """タブ3: 項目不足・差異ありのUI構築"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        desc = QLabel(
            "手元とNotionの双方に存在しますが、お互いに欠けている項目（不足情報）があるシナリオです。\n"
            "［対比・採否選択］を押すと、各項目を見比べながら手元へ反映する情報を個別に選択できます。"
        )
        desc.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 11px; line-height: 1.4;")
        layout.addWidget(desc)

        # テーブル
        self.table_field_lacking = self._create_styled_table(
            ["タイトル", "手元側で不足している項目", "Notion側で不足している項目", "操作"]
        )
        self.table_field_lacking.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table_field_lacking.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table_field_lacking.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_field_lacking.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.table_field_lacking.setColumnWidth(3, 130)
        layout.addWidget(self.table_field_lacking)

        return widget


    def _create_styled_table(self, headers: list[str]) -> QTableWidget:
        """アンティーク調のスタイル付きテーブルウィジェットを生成"""
        tbl = QTableWidget()
        tbl.setColumnCount(len(headers))
        tbl.setHorizontalHeaderLabels(headers)
        tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        tbl.setSelectionMode(QAbstractItemView.SingleSelection)
        tbl.verticalHeader().setVisible(False)
        tbl.setStyleSheet(f"""
            QTableWidget {{
                background-color: #15110d;
                border: 1px solid #3d2f21;
                border-radius: 2px;
                gridline-color: #241c14;
                color: {Theme.TEXT_WHITE};
                font-size: 11px;
            }}
            QTableWidget::item {{
                padding: 4px 6px;
                border-bottom: 1px solid #241c14;
            }}
            QTableWidget::item:selected {{
                background-color: #2d2218;
                color: #ffffff;
            }}
            QHeaderView::section {{
                background-color: #1f1812;
                color: {Theme.BRASS_LIGHT};
                border: none;
                border-bottom: 1px solid #4a3a2a;
                border-right: 1px solid #241c14;
                padding: 5px 6px;
                font-size: 11px;
                font-weight: bold;
                font-family: {Theme.FONT_SERIF};
            }}
        """)
        return tbl

    def _start_audit(self):
        """照合処理を開始"""
        if hasattr(self, "worker") and self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait(1500)

        self.pbar.setVisible(True)
        self.status_label.setText("Notion書架と手元の収蔵録を照合中...")
        self.btn_recheck.setEnabled(False)

        self.worker = NotionAuditWorker(self.db, self)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_audit_finished)
        self.worker.error.connect(self._on_audit_error)
        self.worker.start()

    def closeEvent(self, event):
        """ダイアログ終了時に実行中スレッドを安全に停止"""
        if hasattr(self, "worker") and self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait(2000)
        super().closeEvent(event)


    def _on_progress(self, msg: str):
        self.status_label.setText(msg)

    def _on_audit_finished(self, diff_result: dict):
        self.diff_data = diff_result
        self.client = diff_result.get("client")
        self.data_source_id = diff_result.get("data_source_id")

        self.pbar.setVisible(False)
        self.btn_recheck.setEnabled(True)

        local_only = diff_result.get("local_only", [])
        notion_only = diff_result.get("notion_only", [])
        field_lacking = diff_result.get("field_lacking", [])
        in_sync = diff_result.get("in_sync_count", 0)

        self.status_label.setText(
            f"照合完了: 手元 {diff_result.get('local_total', 0)} 冊 ／ Notion {diff_result.get('notion_total', 0)} 冊"
        )
        self.badge_local_only.setText(f"手元のみ: {len(local_only)} 冊")
        self.badge_notion_only.setText(f"Notionのみ: {len(notion_only)} 冊")
        self.badge_field_lacking.setText(f"項目不足・差異: {len(field_lacking)} 冊")
        self.badge_in_sync.setText(f"完全一致: {in_sync} 冊")

        self.tabs.setTabText(0, f"📘 手元のみ ({len(local_only)})")
        self.tabs.setTabText(1, f"☁️ Notionのみ ({len(notion_only)})")
        self.tabs.setTabText(2, f"⚖️ 項目不足・差異 ({len(field_lacking)})")

        self._populate_local_only_table(local_only)
        self._populate_notion_only_table(notion_only)
        self._populate_field_lacking_table(field_lacking)

    def _on_audit_error(self, err_msg: str):
        self.pbar.setVisible(False)
        self.btn_recheck.setEnabled(True)
        self.status_label.setText("照合エラーが発生しました。")
        message, _, detail = err_msg.partition("\n\n[詳細]\n")
        show_error(self, "Notion と手元の書架を照合する", message, detail=detail, title="照合エラー")

    def _populate_local_only_table(self, items: list[dict]):
        self.table_local_only.setRowCount(0)
        self.table_local_only.setRowCount(len(items))

        for row, it in enumerate(items):
            title = it.get("title") or "無題"
            author = it.get("author") or "-"
            sys_name = it.get("system_name") or "-"
            pl_dur = f"{it.get('players_text') or '-'} / {it.get('duration_text') or '-'}"
            has_thumb = "あり" if it.get("thumbnail") else "なし"

            item_title = QTableWidgetItem(title)
            item_author = QTableWidgetItem(author)
            item_sys = QTableWidgetItem(sys_name)
            item_pl = QTableWidgetItem(pl_dur)
            item_thumb = QTableWidgetItem(has_thumb)

            for col_it in (item_title, item_author, item_sys, item_pl, item_thumb):
                col_it.setFlags(col_it.flags() & ~Qt.ItemIsEditable)

            self.table_local_only.setItem(row, 0, item_title)
            self.table_local_only.setItem(row, 1, item_author)
            self.table_local_only.setItem(row, 2, item_sys)
            self.table_local_only.setItem(row, 3, item_pl)
            self.table_local_only.setItem(row, 4, item_thumb)

            # 操作ボタン（Notionへ書き出し）
            btn = QPushButton("Notionへ登録")
            btn.setFixedSize(100, 24)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #2a1f16;
                    color: {Theme.BRASS_LIGHT};
                    border: 1px solid #4a3a2a;
                    border-radius: 2px;
                    font-size: 11px;
                }}
                QPushButton:hover {{
                    background-color: #3d2c1e;
                    color: #ffffff;
                }}
            """)
            btn.clicked.connect(lambda checked=False, item_id=it["id"]: self._export_single_item(item_id))
            
            btn_container = QWidget()
            btn_container.setStyleSheet("background: transparent;")
            bc_layout = QHBoxLayout(btn_container)
            bc_layout.setContentsMargins(0, 0, 0, 0)
            bc_layout.setAlignment(Qt.AlignCenter)
            bc_layout.addWidget(btn)
            self.table_local_only.setCellWidget(row, 5, btn_container)

    def _populate_notion_only_table(self, pages: list[dict]):
        self.table_notion_only.setRowCount(0)
        self.table_notion_only.setRowCount(len(pages))

        for row, vals in enumerate(pages):
            title = vals.get("title") or "無題"
            author = vals.get("author") or "-"
            raw_tags = vals.get("tags") or []
            tags_str = ", ".join(raw_tags) if isinstance(raw_tags, list) else str(raw_tags or "-")
            has_thumb = "あり" if vals.get("cover_url") else "なし"

            item_title = QTableWidgetItem(title)
            item_author = QTableWidgetItem(author)
            item_tags = QTableWidgetItem(tags_str)
            item_thumb = QTableWidgetItem(has_thumb)

            for col_it in (item_title, item_author, item_tags, item_thumb):
                col_it.setFlags(col_it.flags() & ~Qt.ItemIsEditable)

            self.table_notion_only.setItem(row, 0, item_title)
            self.table_notion_only.setItem(row, 1, item_author)
            self.table_notion_only.setItem(row, 2, item_tags)
            self.table_notion_only.setItem(row, 3, item_thumb)

            # 操作ボタン（手元へ取り込み）
            btn = QPushButton("手元へ取り込み")
            btn.setFixedSize(100, 24)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #1a2a3d;
                    color: #87b9e6;
                    border: 1px solid #2d4563;
                    border-radius: 2px;
                    font-size: 11px;
                }}
                QPushButton:hover {{
                    background-color: #243b57;
                    color: #ffffff;
                }}
            """)
            btn.clicked.connect(lambda checked=False, p_vals=vals: self._import_single_page(p_vals))

            btn_container = QWidget()
            btn_container.setStyleSheet("background: transparent;")
            bc_layout = QHBoxLayout(btn_container)
            bc_layout.setContentsMargins(0, 0, 0, 0)
            bc_layout.setAlignment(Qt.AlignCenter)
            bc_layout.addWidget(btn)
            self.table_notion_only.setCellWidget(row, 4, btn_container)

    def _populate_field_lacking_table(self, diffs: list[dict]):
        self.table_field_lacking.setRowCount(0)
        self.table_field_lacking.setRowCount(len(diffs))

        for row, df in enumerate(diffs):
            title = df.get("title") or "無題"
            local_lack = "、 ".join(df.get("local_missing", [])) or "なし"
            notion_lack = "、 ".join(df.get("notion_missing", [])) or "なし"

            item_title = QTableWidgetItem(title)
            item_local = QTableWidgetItem(local_lack)
            item_notion = QTableWidgetItem(notion_lack)

            item_local.setForeground(Qt.yellow if local_lack != "なし" else Qt.gray)
            item_notion.setForeground(Qt.cyan if notion_lack != "なし" else Qt.gray)

            for col_it in (item_title, item_local, item_notion):
                col_it.setFlags(col_it.flags() & ~Qt.ItemIsEditable)

            self.table_field_lacking.setItem(row, 0, item_title)
            self.table_field_lacking.setItem(row, 1, item_local)
            self.table_field_lacking.setItem(row, 2, item_notion)

            btn = QPushButton("対比・採否選択")
            btn.setFixedSize(110, 24)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #382c1f;
                    color: #ffda73;
                    border: 1px solid #5a452a;
                    border-radius: 2px;
                    font-size: 11px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: #4a3a28;
                    color: #ffffff;
                }}
            """)
            btn.clicked.connect(lambda checked=False, diff_entry=df: self._resolve_single_diff(diff_entry))

            btn_container = QWidget()
            btn_container.setStyleSheet("background: transparent;")
            bc_layout = QHBoxLayout(btn_container)
            bc_layout.setContentsMargins(0, 0, 0, 0)
            bc_layout.setAlignment(Qt.AlignCenter)
            bc_layout.addWidget(btn)
            self.table_field_lacking.setCellWidget(row, 3, btn_container)


    def _run_notion_task(self, work, on_done, error_title, error_prefix, operation=None):
        """Notion との通信を別スレッドで実行する（通信中も画面は固まらない）。

        work(worker_db) は別スレッドで呼ばれる。worker_db はそのスレッド専用の Database。
        """
        if self._busy:
            QMessageBox.information(self, "案内", "Notion との通信中です。完了までお待ちください。")
            return
        self._busy = True
        QApplication.setOverrideCursor(Qt.BusyCursor)
        db_path = getattr(self.db, "db_path", "catalog.db")

        def task():
            from core.database import Database
            worker_db = Database(db_path)
            try:
                return work(worker_db)
            finally:
                worker_db.conn.close()

        def finish(callback, value):
            # ダイアログが先に閉じられていてもカーソルは必ず元に戻す
            QApplication.restoreOverrideCursor()
            if not isValid(self):
                return
            self._busy = False
            callback(value)

        def failed(error):
            show_error(self, operation or error_title, error_prefix.rstrip(":："), exc=error, title=error_title)

        run_async(task, lambda r: finish(on_done, r), lambda e: finish(failed, e))

    def _export_single_item(self, item_id: int):
        """単一のアイテムをNotionへ書き出す"""
        if not self.client or not self.data_source_id:
            QMessageBox.warning(self, "エラー", "Notion接続情報が取得できていません。")
            return
        client, data_source_id = self.client, self.data_source_id

        def done(_page_id):
            # メモリ上のリストから除外して即時反映（重い全件再照合を回避）
            if self.diff_data and "local_only" in self.diff_data:
                self.diff_data["local_only"] = [
                    it for it in self.diff_data["local_only"]
                    if it.get("id") != item_id
                ]
                rem_count = len(self.diff_data["local_only"])
                self.badge_local_only.setText(f"手元のみ: {rem_count} 冊")
                self.tabs.setTabText(0, f"📘 手元のみ ({rem_count})")
                self._populate_local_only_table(self.diff_data["local_only"])

            QMessageBox.information(self, "登録完了", "Notionへ登録しました。")

        self._run_notion_task(
            lambda worker_db: notion_sync.export_single_item_to_notion(worker_db, client, data_source_id, item_id),
            done,
            "エラー",
            "Notionへの登録に失敗しました:",
            operation="手元の本を Notion へ登録する",
        )

    def _import_single_page(self, page_vals: dict):
        """単一のNotionページを手元へ取り込む"""
        if not self.client:
            QMessageBox.warning(self, "エラー", "Notion接続情報が取得できていません。")
            return
        title = page_vals.get("title") or "無題のシナリオ"
        client = self.client

        def done(_item_id):
            # メモリ上のリストから除外して即時反映（重い全件再照合を回避）
            if self.diff_data and "notion_only" in self.diff_data:
                target_pid = page_vals.get("page_id")
                self.diff_data["notion_only"] = [
                    p for p in self.diff_data["notion_only"]
                    if p.get("page_id") != target_pid
                ]
                rem_count = len(self.diff_data["notion_only"])
                self.badge_notion_only.setText(f"Notionのみ: {rem_count} 冊")
                self.tabs.setTabText(1, f"☁️ Notionのみ ({rem_count})")
                self._populate_notion_only_table(self.diff_data["notion_only"])

            QMessageBox.information(self, "取り込み完了", f"『{title}』を書架へ取り込みました。")

        self._run_notion_task(
            lambda worker_db: notion_sync.import_single_page_from_notion(worker_db, client, page_vals),
            done,
            "エラー",
            f"『{title}』の取り込みに失敗しました:",
            operation=f"Notion のページを手元へ取り込む（『{title}』）",
        )

    def _resolve_single_diff(self, diff_entry: dict):
        """手元データとNotionデータの項目差分を比較ダイアログで開く（Notion 側の表紙は別スレッドで取得してから開く）"""
        c_url = (diff_entry.get("notion_vals") or {}).get("cover_url")
        client = self.client
        if not (c_url and client):
            self._open_resolve_dialog(diff_entry, None)
            return

        def download(_worker_db):
            try:
                return client.download(c_url)
            except Exception as e:
                error_log.log_error("Notion 側の表紙を取得する（差分の比較）",
                                    "表紙画像を取得できませんでした（表紙なしで比較を続けます）", exc=e)
                return None

        self._run_notion_task(
            download,
            lambda thumb_bytes: self._open_resolve_dialog(diff_entry, thumb_bytes),
            "差分反映エラー",
            "Notion側の表紙の取得中にエラーが発生しました:",
            operation="Notion 側の表紙を取得する（差分の比較）",
        )

    def _open_resolve_dialog(self, diff_entry: dict, thumb_bytes):
        try:
            local_it = diff_entry.get("local_item", {})
            notion_v = diff_entry.get("notion_vals", {})
            item_id = diff_entry.get("item_id")
            page_id = diff_entry.get("page_id")

            curr_dict = {
                "title": local_it.get("title", ""),
                "author": local_it.get("author", ""),
                "system": local_it.get("system_name", ""),
                "players": local_it.get("players_text", ""),
                "duration": local_it.get("duration_text", ""),
                "overview": local_it.get("overview", ""),
                "synopsis": local_it.get("synopsis", ""),
                "tags": local_it.get("tags", []),
                "thumbnail_bytes": local_it.get("thumbnail"),
            }
            notion_dict = {
                "title": notion_v.get("title", ""),
                "author": notion_v.get("author", ""),
                "system": notion_v.get("system_name", ""),
                "players": notion_v.get("players_text", ""),
                "duration": notion_v.get("duration_text", ""),
                "overview": notion_v.get("overview", ""),
                "synopsis": notion_v.get("synopsis", ""),
                "tags": notion_v.get("tags", []),
                "image_bytes": thumb_bytes,
            }

            dlg = WebInfoComparisonDialog(
                curr_dict,
                notion_dict,
                parent=self,
                source_name="Notion",
                db=self.db,
                item_id=item_id,
            )
            if dlg.exec() == QDialog.Accepted:
                if getattr(dlg, "edited_in_detail", False):
                    # 詳細画面で直接編集された場合
                    if page_id:
                        self.db.set_notion_link(item_id, page_id)
                else:
                    selected_fields = dlg.get_selected_fields()
                    update_vals = dict(notion_v)
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
                    edited_vals = dlg.get_edited_values() if hasattr(dlg, "get_edited_values") else {}
                    if not isinstance(edited_vals, dict):
                        edited_vals = {}
                    for f_key, edited in edited_vals.items():
                        if edited and f_key in field_map:
                            update_vals[field_map[f_key]] = edited
                        elif edited and f_key == "tags":
                            update_vals["tags"] = edited
                    for f_key, val_key in field_map.items():
                        if f_key not in selected_fields:
                            update_vals[val_key] = local_it.get(val_key)
                    if "tags" not in selected_fields:
                        update_vals["tags"] = local_it.get("tags")

                    final_thumb = (
                        thumb_bytes if "cover" in selected_fields else local_it.get("thumbnail")
                    )
                    self.db.save_or_update_from_notion(
                        page_id,
                        update_vals,
                        thumbnail_bytes=final_thumb,
                        last_edited_time=notion_v.get("last_edited_time"),
                    )

                # メモリ上のリストから除外して即時反映（重い全件再照合を回避）
                if self.diff_data and "field_lacking" in self.diff_data:
                    self.diff_data["field_lacking"] = [
                        df for df in self.diff_data["field_lacking"]
                        if df.get("item_id") != item_id
                    ]
                    rem_count = len(self.diff_data["field_lacking"])
                    self.badge_field_lacking.setText(f"項目不足・差異: {rem_count} 冊")
                    self.tabs.setTabText(2, f"⚖️ 項目不足・差異 ({rem_count})")
                    self._populate_field_lacking_table(self.diff_data["field_lacking"])

                QMessageBox.information(self, "反映完了", "項目の反映を完了しました。")
        except Exception as e:
            show_error(self, "Notion との差分を比較・反映する", "差分データの比較・反映中にエラーが発生しました", exc=e,
                       title="差分反映エラー")

    def _export_all_local_only(self):
        """手元のみの全アイテムをNotionへ書き出す"""
        if not self.diff_data or not self.client or not self.data_source_id:
            return
        local_only = self.diff_data.get("local_only", [])
        if not local_only:
            QMessageBox.information(self, "案内", "Notionへ書き出す対象がありません。")
            return

        reply = QMessageBox.question(
            self,
            "書き出し確認",
            f"手元にのみ存在する {len(local_only)} 冊のシナリオをNotionへ登録しますか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply == QMessageBox.Yes:
            client, data_source_id = self.client, self.data_source_id
            targets = list(local_only)

            def export_all(worker_db):
                success = 0
                for it in targets:
                    try:
                        notion_sync.export_single_item_to_notion(worker_db, client, data_source_id, it["id"])
                        success += 1
                    except Exception as e:
                        print(f"Error exporting item {it.get('title')}: {e}")
                return success

            def done(success):
                QMessageBox.information(self, "完了", f"{success} / {len(targets)} 冊をNotionへ登録しました。")
                self._start_audit()

            self._run_notion_task(export_all, done, "エラー", "Notionへの登録に失敗しました:",
                                  operation="手元にしか無い本をまとめて Notion へ登録する")

    def _import_all_notion_only(self):
        """Notionのみの全ページを手元へ取り込む（大量データのため安全な進行同期ダイアログへ誘導）"""
        if not self.diff_data or not self.client:
            return
        notion_only = self.diff_data.get("notion_only", [])
        if not notion_only:
            QMessageBox.information(self, "案内", "手元へ取り込む対象がありません。")
            return

        reply = QMessageBox.question(
            self,
            "一括取り込みの確認",
            f"Notionにのみ存在する {len(notion_only)} 冊のシナリオを書架へ取り込みます。\n\n"
            "データ量が多いため、フリーズ防止と進捗確認ができる「Notion同調ダイアログ」を起動して実行しますか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply == QMessageBox.Yes:
            self._open_sync_dialog()

    def _open_sync_dialog(self):
        """通常のNotionSyncDialogを開く"""
        from .notion_sync_dialog import NotionSyncDialog
        dlg = NotionSyncDialog(self.db, parent=self)
        dlg.exec()
        self._start_audit()

