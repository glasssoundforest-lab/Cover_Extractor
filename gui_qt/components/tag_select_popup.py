"""タグ複数選択ポップアップコンポーネント (gui_qt/components/tag_select_popup.py)

西洋古書・グリモワール調の世界観に合わせたタグ複数選択パネル。
グローバルタグとローカルタグをチェックボックスで複数選択し、
リアルタイムに絞り込みを行えます。
"""

from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QCheckBox,
    QScrollArea,
    QFrame,
)

from ..theme import Theme
from core.database import global_tag_sort_key
from .ornate import OrnateFrame, OrnateDivider


def make_tag_dot(color_hex, size=10):
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color_hex or Theme.BRASS_LIGHT))
    p.drawEllipse(0, 0, size, size)
    p.end()
    return pix


class TagSelectPopup(QFrame):
    """上部ヘッダーバーから呼び出されるタグ複数選択ポップアップ"""
    tags_changed = Signal(list)  # 選択されたタグ名リスト

    def __init__(self, db, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.db = db
        self.selected_tags = set()
        self.checkboxes = {}

        self.setFixedWidth(280)
        self.setFixedHeight(380)
        self.setStyleSheet(f"""
            TagSelectPopup {{
                background-color: #16120e;
                border: 1px solid {Theme.BRASS_LIGHT};
                border-radius: 4px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # ヘッダー
        h_layout = QHBoxLayout()
        title = QLabel("🏷  タグ選択（複数可）")
        title.setStyleSheet(f"""
            color: {Theme.BRASS_LIGHT};
            font-size: 13px;
            font-weight: bold;
            font-family: {Theme.FONT_SERIF};
        """)
        h_layout.addWidget(title)
        h_layout.addStretch()

        clear_btn = QPushButton("全解除")
        clear_btn.setFixedHeight(22)
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #221a14;
                color: {Theme.TEXT_MUTED};
                border: 1px solid #4a3a2a;
                border-radius: 2px;
                padding: 1px 6px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                color: {Theme.BRASS_LIGHT};
                border: 1px solid {Theme.BRASS_BASE};
            }}
        """)
        clear_btn.clicked.connect(self.clear_all)
        h_layout.addWidget(clear_btn)
        layout.addLayout(h_layout)

        layout.addWidget(OrnateDivider(self, height=6))

        # スクロールエリア
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                background: #120e0a;
                width: 8px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {Theme.BRASS_DARK};
                min-height: 20px;
                border-radius: 4px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
                background: transparent;
                border: none;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: transparent;
                border: none;
            }}
        """)

        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background: transparent;")
        self.c_layout = QVBoxLayout(self.scroll_content)
        self.c_layout.setContentsMargins(4, 4, 4, 4)
        self.c_layout.setSpacing(6)
        scroll.setWidget(self.scroll_content)
        layout.addWidget(scroll)

        self.refresh_tags()

    def refresh_tags(self):
        """データベースからグローバルタグとローカルタグを取得してチェックボックスを生成"""
        # 既存ウィジェット即時切り離し・削除
        while self.c_layout.count():
            item = self.c_layout.takeAt(0)
            if item.widget():
                w = item.widget()
                w.setParent(None)
                w.deleteLater()
            elif item.layout():
                while item.layout().count():
                    sub = item.layout().takeAt(0)
                    if sub.widget():
                        sw = sub.widget()
                        sw.setParent(None)
                        sw.deleteLater()
        self.checkboxes.clear()

        # 1. グローバルタグセクション
        g_head = QLabel("❖ グローバルタグ")
        g_head.setStyleSheet(f"color: {Theme.BRASS_LIGHT}; font-size: 12px; font-weight: bold; padding-top: 2px;")
        self.c_layout.addWidget(g_head)

        gtags = self.db.get_global_tags()
        # 優先順: CoC, マダミス, 未通過, 通過済, GM可
        tag_dict = {t[1]: t[2] for t in gtags}
        ordered = sorted([t for t in tag_dict if t != "未設定"], key=global_tag_sort_key)
        ordered.append("未設定")
        tag_dict["未設定"] = "#607d8b"

        for tname in ordered:
            self._add_checkbox_row(tname, tag_dict.get(tname, "#607d8b"), is_global=True)

        # 2. ローカルタグセクション
        self.c_layout.addWidget(OrnateDivider(self, height=8))
        l_head = QLabel("🏷 ローカルタグ")
        l_head.setStyleSheet(f"color: {Theme.BRASS_LIGHT}; font-size: 12px; font-weight: bold; padding-top: 2px;")
        self.c_layout.addWidget(l_head)

        ltags = self.db.get_local_tags()
        if ltags:
            for tid, tname, tcolor, is_glob in ltags:
                self._add_checkbox_row(tname, tcolor or "#546e7a", is_global=False)
        else:
            empty_lbl = QLabel("（登録されたローカルタグはありません）")
            empty_lbl.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 11px; padding: 2px 6px;")
            self.c_layout.addWidget(empty_lbl)

        self.c_layout.addStretch()

    def _add_checkbox_row(self, tname, tcolor, is_global=True):
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        r_layout = QHBoxLayout(row)
        r_layout.setContentsMargins(4, 2, 4, 2)
        r_layout.setSpacing(6)

        dot = QLabel()
        dot.setPixmap(make_tag_dot(tcolor, size=10))
        dot.setFixedSize(12, 12)
        r_layout.addWidget(dot)

        cb = QCheckBox(tname)
        cb.setChecked(tname in self.selected_tags)
        cb.setCursor(Qt.PointingHandCursor)
        cb.setStyleSheet(f"""
            QCheckBox {{
                color: {Theme.TEXT_WHITE};
                font-size: 12px;
                font-family: {Theme.FONT_SERIF};
                spacing: 6px;
            }}
            QCheckBox:hover {{
                color: {Theme.BRASS_LIGHT};
            }}
            QCheckBox::indicator {{
                width: 14px;
                height: 14px;
                border: 1px solid {Theme.BRASS_BASE};
                border-radius: 2px;
                background-color: #1a1511;
            }}
            QCheckBox::indicator:checked {{
                background-color: {Theme.BRASS_BASE};
            }}
        """)
        cb.toggled.connect(lambda checked, name=tname: self._on_checkbox_toggled(name, checked))
        r_layout.addWidget(cb)
        r_layout.addStretch()

        self.c_layout.addWidget(row)
        self.checkboxes[tname] = cb

    def _on_checkbox_toggled(self, tname, checked):
        if checked:
            self.selected_tags.add(tname)
        else:
            self.selected_tags.discard(tname)
        self.tags_changed.emit(list(self.selected_tags))

    def clear_all(self):
        """全タグの選択を解除"""
        for cb in self.checkboxes.values():
            cb.blockSignals(True)
            cb.setChecked(False)
            cb.blockSignals(False)
        self.selected_tags.clear()
        self.tags_changed.emit([])

    def set_selected_tags(self, tags):
        """外部から選択タグを同期"""
        self.selected_tags = set(tags)
        for tname, cb in self.checkboxes.items():
            cb.blockSignals(True)
            cb.setChecked(tname in self.selected_tags)
            cb.blockSignals(False)

    def show_under(self, target_widget):
        """対象ウィジェットの直下にポップアップを表示"""
        self.refresh_tags()
        # 外部ウィジェットのグローバル座標を取得
        gp = target_widget.mapToGlobal(QPoint(0, target_widget.height() + 2))
        self.move(gp)
        self.show()
