"""左側サイドバー（目録分類棚） (gui_qt/components/sidebar.py)

システム分類リスト、しおり・タグフィルター、羽ペンと懐中時計の透かしを表示します。
"""

import os
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QPainter, QColor
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QFrame,
    QLineEdit,
)

from ..theme import Theme
from .ornate import OrnateFrame, OrnateDivider, PillTag, make_fleur_pixmap


class SystemItemWidget(QFrame):
    """システム分類の1行（名前、件数、選択時ハイライト）"""
    clicked = Signal(str)

    def __init__(self, sys_name, count=0, is_selected=False, display_text=None, parent=None):
        super().__init__(parent)
        self.sys_name = sys_name
        self.display_text = display_text or sys_name
        self.count = count
        self.is_selected = is_selected

        self.setFixedHeight(30)
        self.setCursor(Qt.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 2, 10, 2)

        self.label = QLabel(self.display_text)
        layout.addWidget(self.label)
        layout.addStretch()

        self.count_label = QLabel(str(count))
        layout.addWidget(self.count_label)

        self.update_style()

    def update_style(self):
        if self.is_selected:
            self.setStyleSheet(f"""
                SystemItemWidget {{
                    background-color: #2c2218;
                    border: 1px solid {Theme.BRASS_LIGHT};
                    border-radius: 2px;
                }}
            """)
            self.label.setText(f"▶  {self.display_text}")
            self.label.setStyleSheet(f"color: {Theme.BRASS_LIGHT}; font-weight: bold; background: transparent;")
            self.count_label.setStyleSheet(f"color: {Theme.BRASS_LIGHT}; font-weight: bold; background: transparent;")
        else:
            self.setStyleSheet(f"""
                SystemItemWidget {{
                    background-color: transparent;
                    border: 1px solid transparent;
                }}
                SystemItemWidget:hover {{
                    background-color: #221b15;
                    border: 1px solid {Theme.BRASS_DARK};
                }}
            """)
            self.label.setText(f"    {self.display_text}")
            self.label.setStyleSheet(f"color: {Theme.TEXT_WHITE}; font-weight: normal; background: transparent;")
            self.count_label.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-weight: normal; background: transparent;")

    def set_selected(self, selected):
        self.is_selected = selected
        self.update_style()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.sys_name)
        super().mousePressEvent(event)


class PillCategoryButton(QFrame):
    """お気に入りやしおり用の長方形短辺丸型（ピル型）ボタン"""
    clicked = Signal(str)

    def __init__(self, key, text, icon="★", count=0, is_selected=False, icon_color="#f1c40f", parent=None):
        super().__init__(parent)
        self.key = key
        self.display_text = text
        self.icon = icon
        self.count = count
        self.is_selected = is_selected
        self.icon_color = icon_color

        self.setFixedHeight(28)
        self.setCursor(Qt.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 2, 12, 2)
        layout.setSpacing(8)

        self.icon_lbl = QLabel(icon)
        self.icon_lbl.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {icon_color}; background: transparent;")
        layout.addWidget(self.icon_lbl)

        self.text_lbl = QLabel(text)
        self.text_lbl.setStyleSheet(f"font-size: 11px; font-family: {Theme.FONT_SERIF}; background: transparent;")
        layout.addWidget(self.text_lbl)
        layout.addStretch()

        self.count_lbl = QLabel(str(count))
        self.count_lbl.setStyleSheet(f"font-size: 11px; font-weight: bold; background: transparent;")
        layout.addWidget(self.count_lbl)

        self.update_style()

    def update_style(self):
        if self.is_selected:
            bg = "#3a2a1a"
            border = Theme.BRASS_LIGHT
            text_color = Theme.BRASS_LIGHT
            count_color = Theme.BRASS_LIGHT
        else:
            bg = "#1a1511"
            border = "#4a3826"
            text_color = Theme.TEXT_WHITE
            count_color = Theme.TEXT_MUTED

        self.setStyleSheet(f"""
            PillCategoryButton {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 14px;
            }}
            PillCategoryButton:hover {{
                background-color: #2e2217;
                border: 1px solid {Theme.BRASS_LIGHT};
            }}
        """)
        self.text_lbl.setStyleSheet(f"color: {text_color}; font-size: 11px; font-weight: {'bold' if self.is_selected else 'normal'}; background: transparent;")
        self.count_lbl.setStyleSheet(f"color: {count_color}; font-size: 11px; font-weight: bold; background: transparent;")

    def set_selected(self, selected):
        self.is_selected = selected
        self.update_style()

    def set_count(self, count):
        self.count = count
        self.count_lbl.setText(str(count))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.key)
        super().mousePressEvent(event)


class Sidebar(OrnateFrame):
    """書架の目録・分類棚サイドバー（システム分類・お気に入り・しおり・グローバルタグ独立構成）"""
    system_changed = Signal(str)            # 選択システム（"すべて", "__favorite__", "__bookmarked__", or 特定システム名）
    tags_changed = Signal(list)             # 選択されたタグ一覧
    local_tag_search_changed = Signal(str)  # ローカルタグ検索テキスト

    def __init__(self, parent=None):
        # 半透明ダークパネル (alpha: 110 で背景アートの羽ペン・文字・懐中時計が上品に透ける)
        super().__init__(parent, bracket_size=14, bg_color=QColor(20, 16, 12, 110))
        self.setFixedWidth(240)

        self.current_system = "すべて"
        self.selected_tags = set()
        self.system_widgets = {}
        self.tag_widgets = {}

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 14, 12, 14)
        main_layout.setSpacing(8)

        # =====================================================================
        # 1. 「⚜ システム分類」セクション
        # =====================================================================
        head_layout = QHBoxLayout()
        fleur_lbl = QLabel()
        fleur_lbl.setPixmap(make_fleur_pixmap(14, Theme.BRASS_LIGHT))
        head_layout.addWidget(fleur_lbl)

        sys_title = QLabel("システム分類")
        sys_title.setStyleSheet(f"color: {Theme.BRASS_LIGHT}; font-weight: bold; font-family: {Theme.FONT_SERIF}; font-size: 13px; background: transparent;")
        head_layout.addWidget(sys_title)
        head_layout.addStretch()
        main_layout.addLayout(head_layout)

        main_layout.addWidget(OrnateDivider(self, height=8))

        # システム一覧コンテナ
        self.sys_container = QVBoxLayout()
        self.sys_container.setSpacing(3)
        main_layout.addLayout(self.sys_container)

        # =====================================================================
        # 2. 「★ お気に入り」セクション（独立カテゴリ化）
        # =====================================================================
        main_layout.addWidget(OrnateDivider(self, height=10))

        fav_head_layout = QHBoxLayout()
        fav_title = QLabel("★  お気に入り")
        fav_title.setStyleSheet(f"color: #f1c40f; font-weight: bold; font-family: {Theme.FONT_SERIF}; font-size: 13px; background: transparent;")
        fav_head_layout.addWidget(fav_title)
        fav_head_layout.addStretch()
        main_layout.addLayout(fav_head_layout)

        self.fav_button = PillCategoryButton("__favorite__", "お気に入りの書物", icon="★", count=0, is_selected=False, icon_color="#f1c40f", parent=self)
        self.fav_button.clicked.connect(self._on_category_clicked)
        main_layout.addWidget(self.fav_button)

        # =====================================================================
        # 3. 「🔖 しおり」セクション（しおりを挟んだ書物）
        # =====================================================================
        main_layout.addWidget(OrnateDivider(self, height=10))

        bm_head_layout = QHBoxLayout()
        bm_title = QLabel("🔖  しおり")
        bm_title.setStyleSheet(f"color: {Theme.BRASS_LIGHT}; font-weight: bold; font-family: {Theme.FONT_SERIF}; font-size: 13px; background: transparent;")
        bm_head_layout.addWidget(bm_title)
        bm_head_layout.addStretch()
        main_layout.addLayout(bm_head_layout)

        self.bm_button = PillCategoryButton("__bookmarked__", "しおりを挟んだ書物", icon="🔖", count=0, is_selected=False, icon_color="#e2c07d", parent=self)
        self.bm_button.clicked.connect(self._on_category_clicked)
        main_layout.addWidget(self.bm_button)

        # =====================================================================
        # 4. 「🏷 タグ」セクション（グローバルタグのみ！）
        # =====================================================================
        main_layout.addWidget(OrnateDivider(self, height=10))

        tag_head_layout = QHBoxLayout()
        tag_title = QLabel("🏷  タグ")
        tag_title.setStyleSheet(f"color: {Theme.BRASS_LIGHT}; font-weight: bold; font-family: {Theme.FONT_SERIF}; font-size: 13px; background: transparent;")
        tag_head_layout.addWidget(tag_title)
        tag_head_layout.addStretch()
        main_layout.addLayout(tag_head_layout)

        # タグ一覧コンテナ（2列ピル型ボタンスタイル）
        self.tag_container = QWidget()
        self.tag_container.setStyleSheet("background: transparent;")
        self.tag_layout = QVBoxLayout(self.tag_container)
        self.tag_layout.setContentsMargins(0, 0, 0, 0)
        self.tag_layout.setSpacing(6)
        main_layout.addWidget(self.tag_container)

        # 互換用（上部ヘッダーのタグ検索に統合）
        self.local_tag_search_edit = QLineEdit()
        self.local_tag_search_edit.textChanged.connect(self._on_local_search_changed)
        self.local_tag_search_edit.hide()

        main_layout.addStretch()

    def set_systems(self, system_counts, favorite_count=0, bookmark_count=0):
        """システム一覧、お気に入り件数、しおり件数を更新"""
        # 既存ウィジェットのクリア
        while self.sys_container.count():
            item = self.sys_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.system_widgets.clear()

        # 1. "すべて" を先頭に追加
        total = sum(system_counts.values())
        all_item = SystemItemWidget("すべて", total, self.current_system == "すべて")
        all_item.clicked.connect(self._on_category_clicked)
        self.sys_container.addWidget(all_item)
        self.system_widgets["すべて"] = all_item

        # 2. 各システム分類
        for sname, cnt in system_counts.items():
            if not sname:
                continue
            is_sel = (self.current_system == sname)
            w = SystemItemWidget(sname, cnt, is_sel)
            w.clicked.connect(self._on_category_clicked)
            self.sys_container.addWidget(w)
            self.system_widgets[sname] = w

        # 3. お気に入り件数・しおり件数更新
        self.fav_button.set_count(favorite_count)
        self.fav_button.set_selected(self.current_system == "__favorite__")

        self.bm_button.set_count(bookmark_count)
        self.bm_button.set_selected(self.current_system == "__bookmarked__")

    def set_tags(self, tags):
        """グローバルタグ一覧を更新（長方形短辺丸型ピルボタンスタイル）"""
        for w in self.tag_widgets.values():
            w.deleteLater()
        self.tag_widgets.clear()

        # 既存のレイアウト内アイテムをクリア
        while self.tag_layout.count():
            item = self.tag_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                # サブラアウトの削除
                while item.layout().count():
                    sub = item.layout().takeAt(0)
                    if sub.widget():
                        sub.widget().deleteLater()

        # 2列に並べる（長方形短辺丸型ボタン）
        row_layout = None
        for i, tag_item in enumerate(tags):
            if isinstance(tag_item, (list, tuple)):
                tname = tag_item[0]
                tcolor = tag_item[1] if len(tag_item) > 1 else None
            else:
                tname = tag_item
                tcolor = None

            if i % 2 == 0:
                row_layout = QHBoxLayout()
                row_layout.setSpacing(6)
                self.tag_layout.addLayout(row_layout)

            pill = PillTag(tname, color=tcolor, is_checkable=True)
            pill.toggled.connect(self._on_tag_toggled)
            row_layout.addWidget(pill)
            self.tag_widgets[tname] = pill

    def _on_category_clicked(self, key):
        """システム分類・お気に入り・しおりの選択切り替え"""
        self.current_system = key

        # システムウィジェットの選択状態更新
        for name, w in self.system_widgets.items():
            w.set_selected(name == key)

        # お気に入り・しおりボタンの選択状態更新
        self.fav_button.set_selected(key == "__favorite__")
        self.bm_button.set_selected(key == "__bookmarked__")

        self.system_changed.emit(key)

    def _on_local_search_changed(self, text):
        self.local_tag_search_changed.emit(text.strip())

    def _on_tag_toggled(self, tname, checked):
        if tname == "未設定":
            if checked:
                # 「未設定」がONになったら他の通常グローバルタグの選択を全て解除
                for name in list(self.selected_tags):
                    if name != "未設定":
                        self.selected_tags.discard(name)
                        if name in self.tag_widgets:
                            self.tag_widgets[name].is_checked = False
                            self.tag_widgets[name]._update_style()
                self.selected_tags.add("未設定")
            else:
                self.selected_tags.discard("未設定")
        else:
            if checked:
                # 通常タグがONになったら「未設定」を解除
                if "未設定" in self.selected_tags:
                    self.selected_tags.discard("未設定")
                    if "未設定" in self.tag_widgets:
                        self.tag_widgets["未設定"].is_checked = False
                        self.tag_widgets["未設定"]._update_style()
                self.selected_tags.add(tname)
            else:
                self.selected_tags.discard(tname)

        self.tags_changed.emit(list(self.selected_tags))
