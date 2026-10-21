"""上部ヘッダーバーコンポーネント (gui_qt/components/header_bar.py)

タイトル、検索バー、ソートドロップダウン、シナリオ追加ボタン、
および表示サイズ（大・中・小・一覧）と設定を切り替えるバーガーメニューを提供します。
"""

from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import (
    QWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QPushButton,
    QMenu,
    QSizePolicy,
)

from ..theme import Theme
from .ornate import make_fleur_pixmap, make_burger_pixmap
from .tag_select_popup import TagSelectPopup


class HeaderBar(QWidget):
    """上部ヘッダーバー"""
    search_changed = Signal(str)
    search_type_changed = Signal(str)   # "all", "tag", "title", "system"
    tags_selected = Signal(list)        # ポップアップで選択されたタグ名一覧
    sort_changed = Signal(str)
    import_requested = Signal()
    import_url_requested = Signal()
    view_mode_changed = Signal(str)  # "large", "medium", "small", "list"
    settings_requested = Signal()
    notion_sync_requested = Signal()
    notion_diff_requested = Signal()

    def __init__(self, parent=None, db=None, show_title: bool = False):
        super().__init__(parent)
        self.db = db
        self.tag_popup = None
        self.selected_tags = []
        self.setFixedHeight(50)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(10)

        if show_title:
            # 1. アプリタイトル
            fleur_lbl = QLabel()
            fleur_lbl.setPixmap(make_fleur_pixmap(20, Theme.BRASS_LIGHT))
            layout.addWidget(fleur_lbl)

            title = QLabel("魔導書架  ―  TRPG Scenario Archive")
            title.setStyleSheet(f"""
                color: {Theme.BRASS_LIGHT};
                font-size: 16px;
                font-weight: bold;
                font-family: {Theme.FONT_SERIF};
            """)
            layout.addWidget(title)

        # -----------------------------------------------------------------
        # 中央寄せエリアの構築
        # -----------------------------------------------------------------
        # 左側ストレッチ（中央寄せ用）
        layout.addStretch(1)

        center_widget = QWidget()
        center_widget.setStyleSheet("background: transparent;")
        center_layout = QHBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(6)

        # 1. 検索バー外枠コンテナ (真鍮枠・ダーク背景・幅420px・高さ30px)
        #    中に [🏷 タグ選択 ▼] ボタンと [テキスト入力 QLineEdit] を一体化して内包
        self.search_container = QFrame()
        self.search_container.setObjectName("search_container")
        self.search_container.setFixedWidth(420)
        self.search_container.setFixedHeight(30)
        self.search_container.setStyleSheet(f"""
            QFrame#search_container {{
                background-color: #140f0b;
                border: 1px solid #4a3a2a;
                border-radius: 4px;
            }}
            QFrame#search_container:hover {{
                border: 1px solid {Theme.BRASS_BASE};
            }}
            QFrame#search_container:focus-within {{
                border: 1px solid {Theme.BRASS_LIGHT};
                background-color: #1a140e;
            }}
        """)
        sc_layout = QHBoxLayout(self.search_container)
        sc_layout.setContentsMargins(4, 3, 4, 3)
        sc_layout.setSpacing(4)

        # 1-a. 🏷 タグ複数選択ボタン（入力枠内に内包、タグを含まない検索時は非表示になる）
        self.tag_select_btn = QPushButton("🏷 タグ選択 ▼")
        self.tag_select_btn.setFixedHeight(22)
        self.tag_select_btn.setCursor(Qt.PointingHandCursor)
        self.tag_select_btn.setToolTip("クリックして複数のタグ（グローバル・ローカル）を選択・絞り込み")
        self._reset_tag_btn_style()
        self.tag_select_btn.clicked.connect(self._toggle_tag_popup)
        sc_layout.addWidget(self.tag_select_btn)

        # 1-b. テキスト入力欄（枠なし・背景透明でコンテナと一体化、タグボタン消滅時は左端まで拡張）
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("書名、システム、タグで検索...")
        self.search_edit.setToolTip("書名・システム・タグで検索（「未設定」「タグなし」でローカルタグ無を絞り込み）")
        self.search_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.search_edit.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                border: none;
                color: {Theme.TEXT_WHITE};
                font-size: 12px;
                font-family: {Theme.FONT_SANS};
                padding: 0px 4px;
            }}
            QLineEdit:focus {{
                border: none;
                outline: none;
            }}
        """)
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self.search_changed.emit)
        sc_layout.addWidget(self.search_edit)

        center_layout.addWidget(self.search_container)

        # 2. 検索の種類コンボボックス（検索バーの右側に配置）
        self.search_type_combo = QComboBox()
        self.search_type_combo.setFixedWidth(115)
        self.search_type_combo.setFixedHeight(30)
        self.search_type_combo.addItem("❖ すべて検索", "all")
        self.search_type_combo.addItem("🏷 タグ検索", "tag")
        self.search_type_combo.addItem("📖 題名検索", "title")
        self.search_type_combo.addItem("⚜ システム検索", "system")
        self.search_type_combo.currentIndexChanged.connect(self._on_search_type_changed)
        center_layout.addWidget(self.search_type_combo)

        # 3. ソートコンボボックス（書架一覧の枠右上に移設されたため、互換用として非表示保持）
        self.sort_combo = QComboBox()
        self.sort_combo.hide()
        sort_options = [
            ("登録が新しい順", "added_desc"),
            ("登録が古い順", "added_asc"),
            ("題名順（あ→ん）", "title_asc"),
            ("題名順（ん→あ）", "title_desc"),
            ("システム順", "system"),
            ("PL人数順", "players"),
            ("所要時間順", "duration"),
        ]
        for label, val in sort_options:
            self.sort_combo.addItem(label, val)
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)

        layout.addWidget(center_widget)

        # 右側ストレッチ（中央寄せ用）
        layout.addStretch(1)

        # -----------------------------------------------------------------
        # 右端アクションボタン群
        # -----------------------------------------------------------------
        self.add_btn = QPushButton("＋ シナリオを追加")
        self.add_btn.setFixedHeight(30)
        self.add_btn.setCursor(Qt.PointingHandCursor)
        self.add_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #241c14;
                color: {Theme.BRASS_LIGHT};
                border: 1px solid {Theme.BRASS_LIGHT};
                border-radius: 2px;
                padding: 4px 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #382c1f;
                color: #ffffff;
                border: 1px solid #e2c07d;
            }}
        """)
        self.add_btn.clicked.connect(self._show_add_menu)
        layout.addWidget(self.add_btn)

        # 5. バーガーアイコンボタン（三本線メニュー）
        self.burger_btn = QPushButton()
        self.burger_btn.setFixedSize(32, 30)
        self.burger_btn.setCursor(Qt.PointingHandCursor)
        self.burger_btn.setIcon(QIcon(make_burger_pixmap(16, Theme.BRASS_LIGHT)))
        self.burger_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #241c14;
                border: 1px solid {Theme.BRASS_BASE};
                border-radius: 2px;
                padding: 4px;
            }}
            QPushButton:hover {{
                background-color: #382c1f;
                border: 1px solid {Theme.BRASS_LIGHT};
            }}
            QPushButton::menu-indicator {{
                image: none;
            }}
        """)
        self.burger_btn.clicked.connect(self._show_burger_menu)
        layout.addWidget(self.burger_btn)

        # メニューの構築
        self._init_burger_menu()

    def _init_burger_menu(self):
        """バーガーメニューの初期化"""
        self.menu = QMenu(self)

        # 表示サイズ（大・中・小・一覧）- 排他的選択グループ
        self.action_group = QActionGroup(self)
        self.action_group.setExclusive(True)

        self.act_large = QAction("表示: 大", self, checkable=True)
        self.act_large.triggered.connect(lambda: self.view_mode_changed.emit("large"))
        self.action_group.addAction(self.act_large)
        self.menu.addAction(self.act_large)

        # 「中」をデフォルトとして設定
        self.act_medium = QAction("表示: 中（標準）", self, checkable=True)
        self.act_medium.setChecked(True)
        self.act_medium.triggered.connect(lambda: self.view_mode_changed.emit("medium"))
        self.action_group.addAction(self.act_medium)
        self.menu.addAction(self.act_medium)

        self.act_small = QAction("表示: 小", self, checkable=True)
        self.act_small.triggered.connect(lambda: self.view_mode_changed.emit("small"))
        self.action_group.addAction(self.act_small)
        self.menu.addAction(self.act_small)

        self.act_list = QAction("表示: 一覧（2カラム）", self, checkable=True)
        self.act_list.triggered.connect(lambda: self.view_mode_changed.emit("list"))
        self.action_group.addAction(self.act_list)
        self.menu.addAction(self.act_list)

        self.menu.addSeparator()

        # シナリオ追加メニュー項目
        self.act_add_file = QAction("📄  ファイルから追加...", self)
        self.act_add_file.triggered.connect(self.import_requested.emit)
        self.menu.addAction(self.act_add_file)

        self.act_add_url = QAction("🌐  URLから追加 (WEB / Notion)...", self)
        self.act_add_url.triggered.connect(self.import_url_requested.emit)
        self.menu.addAction(self.act_add_url)

        self.menu.addSeparator()

        # Notion同期メニュー項目
        self.act_notion = QAction("✦  Notionと同期...", self)
        self.act_notion.triggered.connect(self.notion_sync_requested.emit)
        self.menu.addAction(self.act_notion)

        # Notion差異・不足照合メニュー項目
        self.act_notion_diff = QAction("❖  Notionと書架の差異・不足照合...", self)
        self.act_notion_diff.triggered.connect(self.notion_diff_requested.emit)
        self.menu.addAction(self.act_notion_diff)

        # 設定メニュー項目
        self.act_settings = QAction("⚙  設定...", self)
        self.act_settings.triggered.connect(self.settings_requested.emit)
        self.menu.addAction(self.act_settings)

    def _show_add_menu(self):
        """「＋ シナリオ追加」ボタンクリック時にファイルまたはURL選択メニューをポップアップ表示"""
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: #1a140f;
                color: #e0d0be;
                border: 1px solid {Theme.BRASS_LIGHT};
                border-radius: 3px;
                padding: 4px;
                font-family: {Theme.FONT_SERIF};
            }}
            QMenu::item {{
                padding: 6px 18px;
                border-radius: 2px;
                font-size: 12px;
            }}
            QMenu::item:selected {{
                background-color: #382c1f;
                color: {Theme.BRASS_LIGHT};
            }}
        """)

        act_file = menu.addAction("📄  ファイル・フォルダから追加 (PDF / ZIP)")
        act_file.triggered.connect(self.import_requested.emit)

        act_url = menu.addAction("🌐  Webサイト / NotionのURLから追加...")
        act_url.triggered.connect(self.import_url_requested.emit)

        pos = self.add_btn.mapToGlobal(QPoint(0, self.add_btn.height() + 2))
        menu.exec(pos)

    def _show_burger_menu(self):
        """バーガーボタンの右端に揃えてメニューをポップアップ表示（画面外へのはみ出し防止）"""
        menu_width = self.menu.sizeHint().width()
        pos = self.burger_btn.mapToGlobal(QPoint(self.burger_btn.width() - menu_width, self.burger_btn.height() + 2))
        self.menu.exec(pos)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            win = self.window()
            if win.isMaximized():
                win.showNormal()
            global_p = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
            self._drag_pos = global_p - win.pos()
            handle = win.windowHandle()
            if handle and hasattr(handle, "startSystemMove"):
                handle.startSystemMove()
            event.accept()

    def mouseMoveEvent(self, event):
        if getattr(self, "_drag_pos", None) is not None and event.buttons() & Qt.LeftButton:
            win = self.window()
            if not win.isMaximized():
                global_p = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
                win.move(global_p - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def _on_sort_changed(self, idx):
        sort_key = self.sort_combo.currentData()
        self.sort_changed.emit(sort_key)

    def set_db(self, db):
        self.db = db
        if self.tag_popup:
            self.tag_popup.db = db
            self.tag_popup.refresh_tags()

    def _on_search_type_changed(self, idx):
        stype = self.search_type_combo.currentData()
        has_tag_search = (stype in ("all", "tag"))

        # タグを含まない検索（題名検索、システム検索など）の場合はタグ選択項目を非表示にする
        self.tag_select_btn.setVisible(has_tag_search)
        if not has_tag_search and self.tag_popup and self.tag_popup.isVisible():
            self.tag_popup.hide()

        if stype == "tag":
            self.search_edit.setPlaceholderText("タグ名で検索（未設定も可）...")
            self.tag_select_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #3d2c1c;
                    color: #ffffff;
                    border: 1px solid {Theme.BRASS_LIGHT};
                    border-radius: 3px;
                    padding: 1px 8px;
                    font-size: 11px;
                    font-weight: bold;
                    font-family: {Theme.FONT_SERIF};
                }}
                QPushButton:hover {{
                    background-color: #4e3925;
                    color: #ffffff;
                }}
            """)
        elif stype == "title":
            self.search_edit.setPlaceholderText("題名で検索...")
            self._reset_tag_btn_style()
        elif stype == "system":
            self.search_edit.setPlaceholderText("システム名で検索...")
            self._reset_tag_btn_style()
        else:
            self.search_edit.setPlaceholderText("書名、システム、タグで検索...")
            self._reset_tag_btn_style()

        self.search_type_changed.emit(stype)

    def _reset_tag_btn_style(self):
        self.tag_select_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #241c14;
                color: {Theme.BRASS_LIGHT};
                border: 1px solid #5a4632;
                border-radius: 3px;
                padding: 1px 8px;
                font-size: 11px;
                font-family: {Theme.FONT_SERIF};
            }}
            QPushButton:hover {{
                background-color: #382c1f;
                border: 1px solid {Theme.BRASS_LIGHT};
                color: #ffffff;
            }}
        """)

    def _toggle_tag_popup(self):
        if not self.db:
            return
        if not self.tag_popup:
            self.tag_popup = TagSelectPopup(self.db, parent=self)
            self.tag_popup.tags_changed.connect(self._on_popup_tags_changed)

        if self.tag_popup.isVisible():
            self.tag_popup.hide()
        else:
            self.tag_popup.set_selected_tags(self.selected_tags)
            self.tag_popup.show_under(self.tag_select_btn)

    def _on_popup_tags_changed(self, tags):
        self.selected_tags = tags
        n = len(tags)
        if n > 0:
            self.tag_select_btn.setText(f"🏷 タグ ({n}件) ▼")
        else:
            self.tag_select_btn.setText("🏷 タグ選択 ▼")
        self.tags_selected.emit(tags)

    def set_selected_tags(self, tags):
        self.selected_tags = list(tags)
        n = len(self.selected_tags)
        if n > 0:
            self.tag_select_btn.setText(f"🏷 タグ ({n}件) ▼")
        else:
            self.tag_select_btn.setText("🏷 タグ選択 ▼")
        if self.tag_popup:
            self.tag_popup.set_selected_tags(self.selected_tags)
