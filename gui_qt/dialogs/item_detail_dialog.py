"""シナリオ詳細・あらすじ編集ダイアログ (gui_qt/dialogs/item_detail_dialog.py)

ユーザーから提示された西洋古書・グリモワール調の見開き画面（1024x903画像）を完璧に再現。
- 外枠全体の真鍮金具ブラケットフレーム (OrnateFrame)
- 左カラム: 表紙画像、表紙変更 (画像選択) ボタン、タグ枠表示、タグ編集ボタン
- 右カラム: ❖ ダイヤ見出しと真鍮ライン（基本情報、情報元のURL、概要、あらすじ）
- 右下: 「✎ 編集」ボタン（編集モード時に「💾 保存」「✕ 取消」に切り替え）
- URL直接クリックによるブラウザ起動
- タグの複数チェック編集ダイアログ
"""

import html
import os
import sys
import subprocess
import urllib.parse
from PySide6.QtCore import Qt, QByteArray, Signal, QUrl, QEvent, QRect, QPoint, QTimer
from PySide6.QtGui import QPixmap, QDesktopServices, QCursor, QKeySequence, QPainter, QPen, QBrush, QColor
from PySide6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QTextEdit,
    QFileDialog,
    QMessageBox,
    QFrame,
    QScrollArea,
    QDialogButtonBox,
    QCheckBox,
    QSizePolicy,
    QApplication,
)

from ..theme import Theme
from ..components.ornate import OrnateFrame, OrnateDivider, PillTag, make_fleur_pixmap, FlowLayout
from ..components.ornate_title_bar import OrnateTitleBar
from .web_info_diff_dialog import WebInfoComparisonDialog
from ..async_task import run_async
from ..error_dialog import show_error
import app_settings
import notion_sync


def make_tag_color_circle(color_hex, size=12):
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(Theme.BRASS_LIGHT), 1))
    p.setBrush(QBrush(QColor(color_hex or "#546e7a")))
    p.drawEllipse(1, 1, size - 2, size - 2)
    p.end()
    return pix


class MultiTagEditDialog(QDialog):
    """西洋古書調のタグ設定ダイアログ（タグ一覧から選択。ローカルタグは追加もできる）

    is_global=True のときはグローバルタグ（CoC・マダミス・未通過など）の一覧から選ぶ。
    """
    def __init__(self, item_id, db, parent=None, is_global=False):
        super().__init__(parent)
        self.item_id = item_id
        self.db = db
        self.is_global = bool(is_global)
        kind = "グローバルタグ" if self.is_global else "ローカルタグ"
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setWindowTitle(f"{kind}の設定")
        self.resize(380, 460)
        self.setStyleSheet(Theme.get_application_stylesheet())

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        self.frame = OrnateFrame(self, bracket_size=14, bg_color="#181310")
        outer_layout.addWidget(self.frame)

        f_layout = QVBoxLayout(self.frame)
        f_layout.setContentsMargins(0, 0, 0, 14)
        f_layout.setSpacing(10)

        # 画面デザイン一体型タイトルバー
        self.title_bar = OrnateTitleBar(f"{kind}の設定", parent=self, show_close=True)
        f_layout.addWidget(self.title_bar)

        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(16, 4, 16, 0)
        layout.setSpacing(10)
        f_layout.addWidget(content_widget)

        if self.is_global:
            sub_head = QLabel("※ このシナリオに付与するグローバルタグを一覧から選択してください。")
        else:
            sub_head = QLabel("※ このシナリオに付与する自由なローカルタグを選択・作成してください。")
        sub_head.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 11px;")
        layout.addWidget(sub_head)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background-color: #16120e; border: 1px solid #4a3a2a; border-radius: 2px;")

        self.container = QWidget()
        self.c_layout = QVBoxLayout(self.container)
        self.c_layout.setContentsMargins(12, 10, 12, 10)
        self.c_layout.setSpacing(8)

        local_tags = self.db.get_global_tags() if self.is_global else self.db.get_local_tags()
        current_local_ids = {t[0] for t in self.db.get_item_tags(self.item_id, is_global=self.is_global)}

        self.checkboxes = {}
        for tag_tuple in local_tags:
            tid = tag_tuple[0]
            tname = tag_tuple[1]
            tcolor = tag_tuple[2] if len(tag_tuple) > 2 else None
            self._add_tag_row(tid, tname, tcolor, is_checked=(tid in current_local_ids))

        if not local_tags:
            self.empty_lbl = QLabel("（登録されたグローバルタグはありません）" if self.is_global
                                    else "（登録されたローカルタグはありません。下の欄から自由に追加できます）")
            self.empty_lbl.setStyleSheet("color: #776655; font-size: 11px; font-style: italic;")
            self.c_layout.addWidget(self.empty_lbl)
        else:
            self.empty_lbl = None

        self.c_layout.addStretch()
        scroll.setWidget(self.container)
        layout.addWidget(scroll)

        # 新規ローカルタグ作成用
        new_tag_bar = QHBoxLayout()
        self.new_tag_in = QLineEdit()
        self.new_tag_in.setPlaceholderText("新しいローカルタグ名を入力...")
        self.new_tag_in.setFixedHeight(28)
        self.new_tag_in.setStyleSheet(f"""
            QLineEdit {{
                background-color: #191410;
                color: #ffffff;
                border: 1px solid {Theme.BRASS_BASE};
                border-radius: 2px;
                padding: 4px 6px;
                font-size: 12px;
            }}
            QLineEdit:focus {{
                border: 1px solid {Theme.BRASS_LIGHT};
            }}
        """)
        self.new_tag_in.returnPressed.connect(self._add_new_tag)
        new_tag_bar.addWidget(self.new_tag_in)

        add_tag_btn = QPushButton("＋ 追加")
        add_tag_btn.setFixedSize(70, 28)
        add_tag_btn.setCursor(Qt.PointingHandCursor)
        add_tag_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #261d15;
                color: {Theme.BRASS_LIGHT};
                border: 1px solid {Theme.BRASS_BASE};
                border-radius: 2px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #3b2c1d;
                border: 1px solid {Theme.BRASS_LIGHT};
                color: #ffffff;
            }}
        """)
        add_tag_btn.clicked.connect(self._add_new_tag)
        new_tag_bar.addWidget(add_tag_btn)
        layout.addLayout(new_tag_bar)
        if self.is_global:
            # グローバルタグの追加・削除は設定画面で行う。ここでは一覧からの選択だけ
            self.new_tag_in.hide()
            add_tag_btn.hide()

        bbox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bbox.accepted.connect(self.accept)
        bbox.rejected.connect(self.reject)
        layout.addWidget(bbox)

    def _add_tag_row(self, tid, tname, tcolor, is_checked=True):
        row_widget = QWidget()
        r_layout = QHBoxLayout(row_widget)
        r_layout.setContentsMargins(0, 0, 0, 0)
        r_layout.setSpacing(6)

        col_lbl = QLabel()
        col_lbl.setPixmap(make_tag_color_circle(tcolor, size=12))
        col_lbl.setFixedSize(14, 14)
        col_lbl.setAlignment(Qt.AlignCenter)
        r_layout.addWidget(col_lbl)

        cb = QCheckBox(tname)
        cb.setChecked(is_checked)
        cb.setCursor(Qt.PointingHandCursor)
        cb.setStyleSheet(f"""
            QCheckBox {{
                color: {Theme.TEXT_WHITE};
                font-size: 13px;
                font-family: {Theme.FONT_SERIF};
                spacing: 6px;
            }}
            QCheckBox:hover {{
                color: {Theme.BRASS_LIGHT};
            }}
            QCheckBox::indicator {{
                width: 15px;
                height: 15px;
                border: 1px solid {Theme.BRASS_BASE};
                border-radius: 2px;
                background-color: #1a1511;
            }}
            QCheckBox::indicator:checked {{
                background-color: {Theme.BRASS_BASE};
            }}
        """)
        r_layout.addWidget(cb)
        r_layout.addStretch()

        self.c_layout.insertWidget(len(self.checkboxes), row_widget)
        self.checkboxes[tid] = cb

    def _add_new_tag(self):
        text = self.new_tag_in.text().strip()
        if not text:
            return
        tid = self.db.add_tag(text, is_global=0)
        if tid and tid not in self.checkboxes:
            if self.empty_lbl:
                self.empty_lbl.hide()
            self._add_tag_row(tid, text, "#546e7a", is_checked=True)
            self.new_tag_in.clear()

    def get_selected_tag_ids(self):
        return [tid for tid, cb in self.checkboxes.items() if cb.isChecked()]


class ItemDetailDialog(QDialog):
    """西洋古書・グリモワール調のシナリオ詳細・あらすじ編集ダイアログ（お手本画像完全準拠）"""
    item_updated = Signal(int)
    item_deleted = Signal(int)  # シナリオを破棄した（書架から消えた）

    def __init__(self, item_id, db, extractor=None, item_ids=None, parent=None):
        super().__init__(parent)
        self.item_id = item_id
        self.db = db
        self.extractor = extractor
        self.is_edit_mode = False
        self._temp_thumb_bytes = None

        # 連続閲覧用IDリストとインデックス
        self.item_ids = list(item_ids) if item_ids else [item_id]
        if self.item_id not in self.item_ids:
            self.item_ids.append(self.item_id)
        self.current_index = self.item_ids.index(self.item_id)

        self.setWindowTitle("異稿 - 紙裏 - あらすじ編集")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setMouseTracking(True)
        self.setStyleSheet(Theme.get_application_stylesheet())

        # ウィンドウサイズ・位置保存用タイマー（リサイズ・移動時のデバウンス保存）
        self._save_geom_timer = QTimer(self)
        self._save_geom_timer.setSingleShot(True)
        self._save_geom_timer.setInterval(400)
        self._save_geom_timer.timeout.connect(self._save_geometry_to_ini)

        self.item_data = self.db.get_item(item_id)
        if not self.item_data:
            self.close()
            return

        self._event_loop = None
        self._is_fully_shown = False

        self._load_shortcuts()
        self._init_ui()
        self._init_window_geometry()
        self._load_values()
        self._update_navigation_buttons()

    def _init_ui(self):
        # ウィンドウ全体を包む真鍮金具付きのアンティークフレーム
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        self.root_frame = OrnateFrame(self, bracket_size=20, bg_color="#120e0b")
        self.root_frame.setMouseTracking(True)
        outer_layout.addWidget(self.root_frame)

        root_layout = QVBoxLayout(self.root_frame)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 画面デザイン一体型の古書調タイトルバー（最大化ボタン有効化）
        self.title_bar = OrnateTitleBar("異稿 - 紙裏 - あらすじ編集", parent=self, show_maximize=True, show_close=True)
        root_layout.addWidget(self.title_bar)

        content_widget = QWidget()
        dialog_layout = QHBoxLayout(content_widget)
        dialog_layout.setContentsMargins(24, 16, 24, 6)
        dialog_layout.setSpacing(24)
        root_layout.addWidget(content_widget, 1)

        # =====================================================================
        # 1. 左側カラム（幅 270px）: 表紙画像・表紙変更ボタン・タグ表示枠・タグ編集ボタン
        # =====================================================================
        left_panel = QWidget()
        left_panel.setFixedWidth(270)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        # 1.1 「表紙画像」見出し + お気に入り切り替えボタン
        cov_head_layout = QHBoxLayout()
        cov_head = QLabel("表紙画像")
        cov_head.setStyleSheet(f"color: {Theme.TEXT_WHITE}; font-size: 14px; font-family: {Theme.FONT_SERIF};")
        cov_head_layout.addWidget(cov_head)
        cov_head_layout.addStretch()

        self.is_favorite = bool(self.db.get_favorite(self.item_id))
        self.is_bookmarked = bool(self.db.get_bookmarked(self.item_id))

        self.fav_toggle_btn = QPushButton()
        self.fav_toggle_btn.setCursor(Qt.PointingHandCursor)
        self.fav_toggle_btn.setFixedHeight(24)
        self.fav_toggle_btn.clicked.connect(self._toggle_favorite)

        self.bm_toggle_btn = QPushButton()
        self.bm_toggle_btn.setCursor(Qt.PointingHandCursor)
        self.bm_toggle_btn.setFixedHeight(24)
        self.bm_toggle_btn.clicked.connect(self._toggle_bookmarked)

        self._update_fav_button_style()
        self._update_bm_button_style()

        cov_head_layout.addWidget(self.fav_toggle_btn)
        cov_head_layout.addWidget(self.bm_toggle_btn)
        left_layout.addLayout(cov_head_layout)

        # 表紙フレーム（ダークな二重線枠）
        self.cover_frame = QFrame()
        self.cover_frame.setFixedSize(270, 185)
        self.cover_frame.setStyleSheet(f"""
            QFrame {{
                background-color: #0d0a08;
                border: 1px solid #3d3023;
                border-radius: 2px;
            }}
        """)
        cf_layout = QVBoxLayout(self.cover_frame)
        cf_layout.setContentsMargins(4, 4, 4, 4)

        self.cover_label = QLabel()
        self.cover_label.setAlignment(Qt.AlignCenter)
        cf_layout.addWidget(self.cover_label)

        # 表紙左上のお気に入りシンボル（アンティーク星バッジ・クリックでもトグル可能）
        self.fav_badge = QLabel("★", self.cover_frame)
        self.fav_badge.setAlignment(Qt.AlignCenter)
        self.fav_badge.setFixedSize(22, 22)
        self.fav_badge.setCursor(Qt.PointingHandCursor)
        self.fav_badge.setToolTip("クリックでお気に入りを切り替え")
        self.fav_badge.setStyleSheet(f"""
            QLabel {{
                background-color: rgba(22, 14, 10, 0.90);
                color: #f1c40f;
                border: 1px solid {Theme.BRASS_LIGHT};
                border-radius: 3px;
                font-size: 12px;
                font-weight: bold;
                padding-bottom: 1px;
            }}
            QLabel:hover {{
                background-color: #2e2417;
                color: #ffffff;
            }}
        """)
        self.fav_badge.mousePressEvent = lambda e: self._toggle_favorite()

        # 表紙左上のしおりシンボル（アンティーク栞バッジ・クリックでもトグル可能）
        self.bm_badge = QLabel("🔖", self.cover_frame)
        self.bm_badge.setAlignment(Qt.AlignCenter)
        self.bm_badge.setFixedSize(22, 22)
        self.bm_badge.setCursor(Qt.PointingHandCursor)
        self.bm_badge.setToolTip("クリックでしおりを切り替え")
        self.bm_badge.setStyleSheet(f"""
            QLabel {{
                background-color: rgba(22, 14, 10, 0.90);
                color: #e2c07d;
                border: 1px solid {Theme.BRASS_LIGHT};
                border-radius: 3px;
                font-size: 11px;
                padding-bottom: 1px;
            }}
            QLabel:hover {{
                background-color: #2e2417;
                color: #ffffff;
            }}
        """)
        self.bm_badge.mousePressEvent = lambda e: self._toggle_bookmarked()

        self._update_cover_badges()

        left_layout.addWidget(self.cover_frame)

        # 表紙変更ボタン
        self.change_cover_btn = QPushButton("表紙を変更 (画像選択)")
        self.change_cover_btn.setFixedHeight(32)
        self.change_cover_btn.setCursor(Qt.PointingHandCursor)
        self.change_cover_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #1a1410;
                color: {Theme.BRASS_LIGHT};
                border: 1px solid #4a3a2a;
                border-radius: 2px;
                font-size: 12px;
                font-family: {Theme.FONT_SERIF};
            }}
            QPushButton:hover {{
                background-color: #281f18;
                border: 1px solid {Theme.BRASS_LIGHT};
                color: #ffffff;
            }}
        """)
        self.change_cover_btn.clicked.connect(self._on_change_cover)
        self.change_cover_btn.hide()  # 閲覧モードでは非表示
        left_layout.addWidget(self.change_cover_btn)

        left_layout.addSpacing(14)

        # 1.2 タグ領域（グローバルタグとローカルタグを分けて表示・編集する）
        # テスト・内部互換用（text()取得用）
        self.tags_box = QLabel("-")
        self.tags_box.hide()

        def make_tag_area(title, edit_label, on_edit):
            head = QLabel(title)
            head.setStyleSheet(f"color: {Theme.TEXT_WHITE}; font-size: 14px; font-family: {Theme.FONT_SERIF};")
            left_layout.addWidget(head)

            # タグ表示枠（長方形の短辺が丸いボタンぽいもの＝PillTag に統一）
            container = QFrame()
            container.setMinimumHeight(44)
            container.setStyleSheet(f"""
                QFrame {{
                    background-color: #14100c;
                    border: 1px solid #3d3023;
                    border-radius: 4px;
                }}
            """)
            flow = QVBoxLayout(container)
            flow.setContentsMargins(8, 8, 8, 8)
            flow.setSpacing(6)
            left_layout.addWidget(container)

            btn = QPushButton(edit_label)
            btn.setFixedHeight(32)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #1a1410;
                    color: {Theme.BRASS_LIGHT};
                    border: 1px solid #4a3a2a;
                    border-radius: 2px;
                    font-size: 12px;
                    font-family: {Theme.FONT_SERIF};
                }}
                QPushButton:hover {{
                    background-color: #281f18;
                    border: 1px solid {Theme.BRASS_LIGHT};
                    color: #ffffff;
                }}
            """)
            btn.clicked.connect(on_edit)
            btn.hide()  # 閲覧モードでは非表示
            left_layout.addWidget(btn)
            return container, flow, btn

        self.global_tags_container, self.global_flow_layout, self.edit_global_tags_btn = make_tag_area(
            "グローバルタグ", "🔖  グローバルタグを編集", self._on_edit_global_tags)
        left_layout.addSpacing(8)
        self.tags_container, self.tags_flow_layout, self.edit_tags_btn = make_tag_area(
            "ローカルタグ", "🏷  ローカルタグを編集", self._on_edit_tags)

        # シナリオ破棄ボタン
        self.discard_btn = QPushButton("🗑  このシナリオを破棄")
        self.discard_btn.setFixedHeight(32)
        self.discard_btn.setCursor(Qt.PointingHandCursor)
        self.discard_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #1a1410;
                color: #d98c8c;
                border: 1px solid #5a3030;
                border-radius: 2px;
                font-size: 12px;
                font-family: {Theme.FONT_SERIF};
            }}
            QPushButton:hover {{
                background-color: #3a1c1c;
                border: 1px solid #d98c8c;
                color: #ffffff;
            }}
            QPushButton:disabled {{
                color: #6a5050;
            }}
        """)
        self.discard_btn.clicked.connect(self._on_discard_clicked)
        self.discard_btn.hide()  # 閲覧モードでは非表示
        left_layout.addWidget(self.discard_btn)

        left_layout.addStretch()
        dialog_layout.addWidget(left_panel)

        # =====================================================================
        # 2. 右側カラム: クラシカル見出し（❖ ダイヤ＋真鍮ライン）と各情報セクション
        # =====================================================================
        right_container = QWidget()
        right_main_layout = QVBoxLayout(right_container)
        right_main_layout.setContentsMargins(0, 0, 0, 0)
        right_main_layout.setSpacing(10)

        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.NoFrame)
        right_scroll.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: #14100c;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #3d2f21;
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #bfa990;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
                background: transparent;
                border: none;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
                border: none;
            }
        """)

        right_panel = QWidget()
        right_panel.setStyleSheet("background: transparent;")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 6, 0)
        right_layout.setSpacing(14)

        # 2.1 「❖ 基本情報 ―――――― ⚜ ――――――」
        right_layout.addLayout(self._create_section_header("基本情報"))

        # 基本情報グリッド
        meta_grid = QGridLayout()
        meta_grid.setContentsMargins(12, 0, 12, 4)
        meta_grid.setHorizontalSpacing(24)
        meta_grid.setVerticalSpacing(8)

        fields = [
            ("読み仮名", "kana", 0),
            ("題名", "title", 1),
            ("作者", "author", 2),
            ("システム", "system", 3),
            ("PL人数", "players", 4),
            ("所要時間", "duration", 5),
        ]
        self.view_labels = {}
        self.edit_inputs = {}

        for label_text, key, row in fields:
            lbl = QLabel(label_text)
            lbl.setFixedWidth(70)
            lbl.setStyleSheet("color: #bfa990; font-size: 13px; font-family: serif;")
            meta_grid.addWidget(lbl, row, 0)

            # 閲覧用テキストラベル
            v_lbl = QLabel("-")
            v_lbl.setStyleSheet("color: #f2e6d6; font-size: 13px; font-family: serif;")
            meta_grid.addWidget(v_lbl, row, 1)
            self.view_labels[key] = v_lbl

            # 編集用入力フィールド
            e_in = QLineEdit()
            e_in.setStyleSheet(f"""
                QLineEdit {{
                    background-color: #191410;
                    color: #ffffff;
                    border: 1px solid {Theme.BRASS_BASE};
                    border-radius: 2px;
                    padding: 3px 6px;
                    font-size: 13px;
                }}
            """)
            e_in.hide()
            meta_grid.addWidget(e_in, row, 1)
            self.edit_inputs[key] = e_in

        # 備考・特集掲載リンク（存在する場合に表示）
        self.extra_note_label = QLabel()
        self.extra_note_label.setStyleSheet(f"color: {Theme.BRASS_LIGHT}; font-size: 12px; text-decoration: underline;")
        self.extra_note_label.setCursor(Qt.PointingHandCursor)
        self.extra_note_label.hide()
        meta_grid.addWidget(self.extra_note_label, 6, 1)

        right_layout.addLayout(meta_grid)

        # 2.2 「❖ 情報元 ――――――――――――」
        right_layout.addLayout(self._create_section_header("情報元"))

        self.source_container = QWidget()
        source_main_layout = QVBoxLayout(self.source_container)
        source_main_layout.setContentsMargins(12, 0, 12, 0)
        source_main_layout.setSpacing(6)

        # 閲覧モード用（ファイル、WEBサイト、Notionの順に横並び・はみ出る場合は2行に折り返し）
        self.source_view_widget = QWidget()
        self.source_view_layout = FlowLayout(self.source_view_widget, margin=0, h_spacing=20, v_spacing=6)

        # 1. 登録元ファイルまたはフォルダのリンク表示
        self.file_item_widget = QWidget()
        file_item_layout = QHBoxLayout(self.file_item_widget)
        file_item_layout.setContentsMargins(0, 0, 0, 0)
        file_item_layout.setSpacing(4)

        self.file_link_label = QLabel("-")
        self.file_link_label.setCursor(Qt.PointingHandCursor)
        self.file_link_label.setStyleSheet(f"""
            QLabel {{
                color: {Theme.BRASS_LIGHT};
                font-size: 13px;
                font-family: {Theme.FONT_SERIF};
                text-decoration: underline;
            }}
            QLabel:hover {{
                color: #ffffff;
            }}
        """)
        self.file_link_label.mousePressEvent = lambda e: self._on_file_link_clicked()
        file_item_layout.addWidget(self.file_link_label)
        self.source_view_layout.addWidget(self.file_item_widget)

        # 2. Web情報元URLのリンク表示（登録ドメイン省略名対応＋未登録時のクイック登録ボタン）
        self.web_item_widget = QWidget()
        web_item_layout = QHBoxLayout(self.web_item_widget)
        web_item_layout.setContentsMargins(0, 0, 0, 0)
        web_item_layout.setSpacing(8)

        self.url_label = QLabel("-")
        self.url_label.setCursor(Qt.PointingHandCursor)
        self.url_label.setStyleSheet(f"""
            QLabel {{
                color: {Theme.BRASS_LIGHT};
                font-size: 13px;
                font-family: {Theme.FONT_SERIF};
                text-decoration: underline;
            }}
            QLabel:hover {{
                color: #ffffff;
            }}
        """)
        self.url_label.mousePressEvent = lambda e: self._on_url_clicked()
        web_item_layout.addWidget(self.url_label)

        self.view_add_domain_btn = QPushButton("＋ ドメイン登録")
        self.view_add_domain_btn.setFixedSize(96, 22)
        self.view_add_domain_btn.setCursor(Qt.PointingHandCursor)
        self.view_add_domain_btn.setStyleSheet(f"""
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
        self.view_add_domain_btn.clicked.connect(lambda: self._on_add_domain_clicked())
        self.view_add_domain_btn.hide()
        web_item_layout.addWidget(self.view_add_domain_btn)
        self.source_view_layout.addWidget(self.web_item_widget)

        # 3. Notion情報元のリンク表示（Notionから取り込んだ／連携している場合）
        self.notion_item_widget = QWidget()
        notion_item_layout = QHBoxLayout(self.notion_item_widget)
        notion_item_layout.setContentsMargins(0, 0, 0, 0)
        notion_item_layout.setSpacing(8)

        self.notion_link_label = QLabel("-")
        self.notion_link_label.setCursor(Qt.PointingHandCursor)
        self.notion_link_label.setStyleSheet(f"""
            QLabel {{
                color: {Theme.BRASS_LIGHT};
                font-size: 13px;
                font-family: {Theme.FONT_SERIF};
                text-decoration: underline;
            }}
            QLabel:hover {{
                color: #ffffff;
            }}
        """)
        self.notion_link_label.mousePressEvent = lambda e: self._on_notion_link_clicked(e)
        notion_item_layout.addWidget(self.notion_link_label)

        self.notion_copy_btn = QPushButton("📋 共有リンクをコピー")
        self.notion_copy_btn.setFixedSize(130, 22)
        self.notion_copy_btn.setCursor(Qt.PointingHandCursor)
        self.notion_copy_btn.setToolTip("Notionの共有リンクをクリップボードにコピーします")
        self.notion_copy_btn.setStyleSheet(f"""
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
        self.notion_copy_btn.clicked.connect(self._on_copy_notion_link)
        self.notion_copy_btn.hide()
        notion_item_layout.addWidget(self.notion_copy_btn)
        self.source_view_layout.addWidget(self.notion_item_widget)

        # 4. 情報元が何もない場合の未設定表示
        self.none_source_label = QLabel("未設定")
        self.none_source_label.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 13px; font-family: {Theme.FONT_SERIF};")
        self.none_source_label.hide()
        self.source_view_layout.addWidget(self.none_source_label)

        source_main_layout.addWidget(self.source_view_widget)

        # 編集モード用（登録ファイル表示、URL入力欄、Web情報取得、ドメイン登録）
        self.source_edit_widget = QWidget()
        source_edit_layout = QVBoxLayout(self.source_edit_widget)
        source_edit_layout.setContentsMargins(0, 0, 0, 0)
        source_edit_layout.setSpacing(4)

        self.file_path_edit_lbl = QLabel("-")
        self.file_path_edit_lbl.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 11px;")
        source_edit_layout.addWidget(self.file_path_edit_lbl)

        self.notion_status_edit_lbl = QLabel("")
        self.notion_status_edit_lbl.setStyleSheet(f"color: {Theme.BRASS_LIGHT}; font-size: 11px; font-family: {Theme.FONT_SERIF};")
        source_edit_layout.addWidget(self.notion_status_edit_lbl)

        url_edit_box = QHBoxLayout()
        url_edit_box.setContentsMargins(0, 0, 0, 0)
        url_edit_box.setSpacing(6)

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("情報元URL (https://booth.pm/... など)")
        self.url_edit.setStyleSheet(f"""
            QLineEdit {{
                background-color: #191410;
                color: #ffffff;
                border: 1px solid {Theme.BRASS_BASE};
                border-radius: 2px;
                padding: 4px 6px;
                font-size: 13px;
            }}
        """)
        self.url_edit.textChanged.connect(self._on_url_edit_text_changed)
        url_edit_box.addWidget(self.url_edit, 1)

        self.fetch_web_btn = QPushButton("🌐  Web情報取得")
        self.fetch_web_btn.setFixedSize(115, 28)
        self.fetch_web_btn.setCursor(Qt.PointingHandCursor)
        self.fetch_web_btn.setToolTip("URLのWebページからタイトル・作者・システム・人数・時間・あらすじ・表紙画像を自動取得します")
        self.fetch_web_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #2e2417;
                color: {Theme.BRASS_LIGHT};
                border: 1px solid {Theme.BRASS_BASE};
                border-radius: 2px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #443522;
                border: 1px solid {Theme.BRASS_LIGHT};
                color: #ffffff;
            }}
            QPushButton:disabled {{
                background-color: #1a1511;
                color: {Theme.TEXT_MUTED};
                border: 1px solid #3d2f21;
            }}
        """)
        self.fetch_web_btn.clicked.connect(self._on_fetch_web_info)
        url_edit_box.addWidget(self.fetch_web_btn)

        self.edit_add_domain_btn = QPushButton("＋ ドメイン登録")
        self.edit_add_domain_btn.setFixedSize(96, 28)
        self.edit_add_domain_btn.setCursor(Qt.PointingHandCursor)
        self.edit_add_domain_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #261d15;
                color: {Theme.BRASS_LIGHT};
                border: 1px solid {Theme.BRASS_BASE};
                border-radius: 2px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: #3b2c1d;
                border: 1px solid {Theme.BRASS_LIGHT};
                color: #ffffff;
            }}
        """)
        self.edit_add_domain_btn.clicked.connect(lambda: self._on_add_domain_clicked())
        self.edit_add_domain_btn.hide()
        url_edit_box.addWidget(self.edit_add_domain_btn)

        source_edit_layout.addLayout(url_edit_box)
        self.source_edit_widget.hide()
        source_main_layout.addWidget(self.source_edit_widget)


        right_layout.addWidget(self.source_container)

        # 2.3 「❖ 概要 ――――――――――――」
        right_layout.addLayout(self._create_section_header("概要"))

        ov_container = QWidget()
        ov_layout = QVBoxLayout(ov_container)
        ov_layout.setContentsMargins(12, 0, 12, 0)

        self.overview_label = QLabel("概要なし")
        self.overview_label.setWordWrap(True)
        self.overview_label.setStyleSheet("color: #dcd0bd; font-size: 13px; font-family: serif; line-height: 1.6;")
        ov_layout.addWidget(self.overview_label)

        self.overview_edit = QTextEdit()
        self.overview_edit.setFixedHeight(75)
        self.overview_edit.setStyleSheet(f"""
            QTextEdit {{
                background-color: #191410;
                color: #ffffff;
                border: 1px solid {Theme.BRASS_BASE};
                border-radius: 2px;
                padding: 6px;
                font-size: 13px;
                line-height: 1.4;
            }}
        """)
        self.overview_edit.hide()
        ov_layout.addWidget(self.overview_edit)
        right_layout.addWidget(ov_container)

        # 2.4 「❖ あらすじ ――――――――――――」
        right_layout.addLayout(self._create_section_header("あらすじ"))

        syn_container = QWidget()
        syn_layout = QVBoxLayout(syn_container)
        syn_layout.setContentsMargins(12, 0, 12, 0)

        self.synopsis_label = QLabel("あらすじなし")
        self.synopsis_label.setWordWrap(True)
        self.synopsis_label.setStyleSheet("color: #dcd0bd; font-size: 13px; font-family: serif; line-height: 1.7;")
        syn_layout.addWidget(self.synopsis_label)

        self.synopsis_edit = QTextEdit()
        self.synopsis_edit.setFixedHeight(120)
        self.synopsis_edit.setStyleSheet(f"""
            QTextEdit {{
                background-color: #191410;
                color: #ffffff;
                border: 1px solid {Theme.BRASS_BASE};
                border-radius: 2px;
                padding: 6px;
                font-size: 13px;
                line-height: 1.4;
            }}
        """)
        self.synopsis_edit.hide()
        syn_layout.addWidget(self.synopsis_edit)
        right_layout.addWidget(syn_container)

        # 2.5 「❖ セッション履歴 ――――――――――――」＋「＋ 記録を追加」ボタン（編集画面のみ）
        playlog_header_layout = QHBoxLayout()
        playlog_header_layout.setContentsMargins(0, 0, 0, 0)
        playlog_header_layout.setSpacing(10)

        pl_icon = QLabel("❖")
        pl_icon.setStyleSheet(f"color: {Theme.BRASS_BASE}; font-size: 15px;")
        pl_icon.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        playlog_header_layout.addWidget(pl_icon)

        pl_title = QLabel("セッション履歴")
        pl_title.setStyleSheet(f"""
            color: {Theme.BRASS_LIGHT};
            font-size: 15px;
            font-weight: bold;
            font-family: {Theme.FONT_SERIF};
        """)
        pl_title.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        playlog_header_layout.addWidget(pl_title)

        pl_divider = OrnateDivider(self, height=12)
        pl_divider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        playlog_header_layout.addWidget(pl_divider)

        self.add_playlog_btn = QPushButton("＋  記録を追加")
        self.add_playlog_btn.setFixedSize(100, 26)
        self.add_playlog_btn.setCursor(Qt.PointingHandCursor)
        self.add_playlog_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #261d15;
                color: {Theme.BRASS_LIGHT};
                border: 1px solid {Theme.BRASS_BASE};
                border-radius: 2px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #3b2c1d;
                border: 1px solid {Theme.BRASS_LIGHT};
                color: #ffffff;
            }}
        """)
        self.add_playlog_btn.clicked.connect(self._on_add_play_log)
        self.add_playlog_btn.hide()
        playlog_header_layout.addWidget(self.add_playlog_btn)
        right_layout.addLayout(playlog_header_layout)

        self.playlog_container = QWidget()
        self.playlog_layout = QVBoxLayout(self.playlog_container)
        self.playlog_layout.setContentsMargins(12, 0, 12, 0)
        self.playlog_layout.setSpacing(8)
        right_layout.addWidget(self.playlog_container)

        right_layout.addStretch()

        right_scroll.setWidget(right_panel)
        right_main_layout.addWidget(right_scroll, 1)

        # 2.6 下部アクションバー（中央: ◀ 前の書物 / インジケーター / 次の書物 ▶、右: ✎ 編集 / 💾 保存 / ✕ 取消）
        #     ページめくりはバーの中央に置く。右側のボタンが多くて 1 行では中央に置けない幅のときは、
        #     ページめくりを 1 段上の行の中央に移す（_layout_bottom_bar）
        self._bottom_bar = QWidget()
        self._bottom_grid = QGridLayout(self._bottom_bar)
        # 左右の余白を同じにして、バーの中央＝詳細画面の中央にする
        self._bottom_grid.setContentsMargins(24, 6, 24, 18)
        # 列の間隔は 0 にする（中身の無い左の列の横には間隔が付かず、左右がずれるため）
        self._bottom_grid.setHorizontalSpacing(0)
        self._bottom_grid.setVerticalSpacing(6)
        self._bottom_two_rows = None

        self._nav_box = QWidget()
        nav_bar = QHBoxLayout(self._nav_box)
        nav_bar.setContentsMargins(0, 0, 0, 0)
        nav_bar.setSpacing(10)
        # 右側のボタン: 上の段に「Notionと同期」、下の段に「編集」または「保存」「取消」
        self._action_box = QWidget()
        action_rows = QVBoxLayout(self._action_box)
        action_rows.setContentsMargins(0, 0, 0, 0)
        action_rows.setSpacing(6)
        notion_row = QHBoxLayout()
        notion_row.setContentsMargins(0, 0, 0, 0)
        btn_bar = QHBoxLayout()
        btn_bar.setContentsMargins(0, 0, 0, 0)
        btn_bar.setSpacing(10)
        action_rows.addLayout(notion_row)
        action_rows.addLayout(btn_bar)
        self._action_spacing = btn_bar.spacing()

        # ページめくりボタン群
        self.prev_btn = QPushButton("◀  前の書物")
        self.prev_btn.setFixedSize(105, 32)
        self.prev_btn.setCursor(Qt.PointingHandCursor)
        self.prev_btn.setToolTip("前のシナリオへめくる (←キー / PageUp)")
        self.prev_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #201812;
                color: {Theme.BRASS_LIGHT};
                border: 1px solid {Theme.BRASS_BASE};
                border-radius: 2px;
                font-size: 12px;
                font-family: {Theme.FONT_SERIF};
            }}
            QPushButton:hover {{
                background-color: #33251a;
                border: 1px solid {Theme.BRASS_LIGHT};
                color: #ffffff;
            }}
            QPushButton:disabled {{
                background-color: #140f0c;
                color: #554433;
                border: 1px solid #2a1f16;
            }}
        """)
        self.prev_btn.clicked.connect(self._go_prev)
        nav_bar.addWidget(self.prev_btn)

        self.page_indicator = QLabel("―  1 / 1 冊  ―")
        self.page_indicator.setAlignment(Qt.AlignCenter)
        self.page_indicator.setStyleSheet(f"""
            color: {Theme.BRASS_LIGHT};
            font-size: 12px;
            font-family: {Theme.FONT_SERIF};
            font-weight: bold;
            padding: 0 8px;
        """)
        nav_bar.addWidget(self.page_indicator)

        self.next_btn = QPushButton("次の書物  ▶")
        self.next_btn.setFixedSize(105, 32)
        self.next_btn.setCursor(Qt.PointingHandCursor)
        self.next_btn.setToolTip("次のシナリオへめくる (→キー / PageDown)")
        self.next_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #201812;
                color: {Theme.BRASS_LIGHT};
                border: 1px solid {Theme.BRASS_BASE};
                border-radius: 2px;
                font-size: 12px;
                font-family: {Theme.FONT_SERIF};
            }}
            QPushButton:hover {{
                background-color: #33251a;
                border: 1px solid {Theme.BRASS_LIGHT};
                color: #ffffff;
            }}
            QPushButton:disabled {{
                background-color: #140f0c;
                color: #554433;
                border: 1px solid #2a1f16;
            }}
        """)
        self.next_btn.clicked.connect(self._go_next)
        nav_bar.addWidget(self.next_btn)

        self.edit_btn = QPushButton("✎  編集")
        self.edit_btn.setFixedSize(96, 32)
        self.edit_btn.setCursor(Qt.PointingHandCursor)
        self.edit_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #221a14;
                color: {Theme.BRASS_LIGHT};
                border: 1px solid {Theme.BRASS_BASE};
                border-radius: 2px;
                font-size: 13px;
                font-family: {Theme.FONT_SERIF};
            }}
            QPushButton:hover {{
                background-color: #36291e;
                border: 1px solid {Theme.BRASS_LIGHT};
                color: #ffffff;
            }}
        """)
        self.edit_btn.clicked.connect(self._toggle_edit_mode)
        btn_bar.addWidget(self.edit_btn)

        # Notion から取り込んだシナリオだけ、編集中に Notion の最新の内容を取ってこられるようにする
        self.notion_sync_btn = QPushButton("📓  Notionと同期")
        self.notion_sync_btn.setFixedSize(186, 30)  # 下の段の「保存」「取消」と同じ幅
        self.notion_sync_btn.setCursor(Qt.PointingHandCursor)
        self.notion_sync_btn.setToolTip("Notion から最新の内容を取得し、手元の内容と比べて反映する項目を選べます")
        self.notion_sync_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #1d1a16;
                color: {Theme.TEXT_WHITE};
                border: 1px solid {Theme.BRASS_BASE};
                border-radius: 2px;
                font-size: 12px;
                font-family: {Theme.FONT_SERIF};
            }}
            QPushButton:hover {{
                background-color: #2c251d;
                border: 1px solid {Theme.BRASS_LIGHT};
                color: #ffffff;
            }}
            QPushButton:disabled {{
                color: {Theme.TEXT_MUTED};
                border: 1px solid #4a3a2a;
            }}
        """)
        self.notion_sync_btn.clicked.connect(self._on_notion_sync_clicked)
        self.notion_sync_btn.hide()
        notion_row.addStretch()
        notion_row.addWidget(self.notion_sync_btn)
        self._notion_fetch_task = None
        self._discard_task = None

        self.save_btn = QPushButton("💾  保存")
        self.save_btn.setFixedSize(96, 32)
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #2e2417;
                color: {Theme.BRASS_LIGHT};
                border: 1px solid {Theme.BRASS_LIGHT};
                border-radius: 2px;
                font-size: 13px;
                font-weight: bold;
                font-family: {Theme.FONT_SERIF};
            }}
            QPushButton:hover {{
                background-color: #443522;
                color: #ffffff;
            }}
        """)
        self.save_btn.clicked.connect(self._on_save)
        self.save_btn.hide()
        btn_bar.addWidget(self.save_btn)

        self.cancel_btn = QPushButton("✕  取消")
        self.cancel_btn.setFixedSize(80, 32)
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.setStyleSheet(f"""
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
        self.cancel_btn.clicked.connect(self._on_cancel)
        self.cancel_btn.hide()
        btn_bar.addWidget(self.cancel_btn)

        dialog_layout.addWidget(right_container, 1)

        # 下部バーは左右の列の下に、詳細画面の幅いっぱいに置く（ページめくりを詳細画面の中央に置くため）
        root_layout.addWidget(self._bottom_bar)


    def _create_section_header(self, title_text):
        """お手本画像通りの『❖ タイトル ―――― ⚜ ――――』見出しレイアウトを構築"""
        h_layout = QHBoxLayout()
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(10)

        # ❖ ダイヤアイコン
        icon_lbl = QLabel("❖")
        icon_lbl.setStyleSheet(f"color: {Theme.BRASS_BASE}; font-size: 15px;")
        icon_lbl.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        h_layout.addWidget(icon_lbl)

        # タイトル
        title_lbl = QLabel(title_text)
        title_lbl.setStyleSheet(f"""
            color: {Theme.BRASS_LIGHT};
            font-size: 15px;
            font-weight: bold;
            font-family: {Theme.FONT_SERIF};
        """)
        title_lbl.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        h_layout.addWidget(title_lbl)

        # 右側に伸びるアンティーク真鍮ライン
        divider = OrnateDivider(self, height=12)
        divider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        h_layout.addWidget(divider)

        return h_layout

    def _update_cover_preview(self, thumb_bytes=None):
        """表紙画像プレビューの更新"""
        if thumb_bytes is None:
            it = self.db.get_item(self.item_id)
            thumb_bytes = it[8] if it else None

        if thumb_bytes:
            pix = QPixmap()
            if pix.loadFromData(QByteArray(thumb_bytes)) and not pix.isNull():
                self.cover_label.setPixmap(pix.scaled(262, 177, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                self.cover_label.setText("表紙画像なし")
        else:
            self.cover_label.setText("表紙画像なし")

    def _render_tags(self):
        """タグの描画（グローバルタグとローカルタグの領域を分け、長方形の短辺が丸いボタン＝PillTagで表示）"""
        item_tags = self.db.get_item_tags(self.item_id)
        self.tags_box.setText("、".join(t[1] for t in item_tags) if item_tags else "タグなし")
        self._fill_tag_flow(self.global_flow_layout, [t for t in item_tags if t[3]], "グローバルタグなし")
        self._fill_tag_flow(self.tags_flow_layout, [t for t in item_tags if not t[3]], "ローカルタグなし")

    def _fill_tag_flow(self, flow_layout, rows, empty_text):
        while flow_layout.count():
            item = flow_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                while item.layout().count():
                    sub = item.layout().takeAt(0)
                    if sub.widget():
                        sub.widget().deleteLater()
        if not rows:
            empty_lbl = QLabel(empty_text)
            empty_lbl.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 11px; padding: 4px;")
            flow_layout.addWidget(empty_lbl)
            return
        row_layout = None
        for i, (_tid, tname, tcolor, _is_glob) in enumerate(rows):
            if i % 2 == 0:
                row_layout = QHBoxLayout()
                row_layout.setSpacing(6)
                flow_layout.addLayout(row_layout)
            row_layout.addWidget(PillTag(tname, color=tcolor, is_checkable=False))
        if len(rows) % 2 != 0 and row_layout is not None:
            row_layout.addStretch()

    def _load_values(self, force_edit_inputs=False):
        """データベースから最新値をロードして表示。
        編集モード中（is_edit_mode=True）かつ force_edit_inputs=False の場合は、
        ユーザーが入力中のテキストが上書き・リセットされないよう保護する。
        """
        it = self.db.get_item(self.item_id)
        if not it:
            return

        # 表紙画像の表示
        self._update_cover_preview(it[8])

        # フィールド設定
        title = it[2] or ""
        system = it[3] or ""
        players = it[4] or ""
        duration = it[5] or ""
        overview = it[6] or ""
        synopsis = it[7] or ""
        kana = self.db.get_title_kana(self.item_id) or ""
        author = self.db.get_author(self.item_id) or ""
        url = self.db.get_source_url(self.item_id) or ""

        self.view_labels["kana"].setText(kana or "未設定")
        self.view_labels["title"].setText(title or "未設定")
        self.view_labels["author"].setText(author or "未設定")
        self.view_labels["system"].setText(system or "未設定")
        self.view_labels["players"].setText(f"{players} 人" if players and not players.endswith("人") else (players or "未設定"))
        self.view_labels["duration"].setText(f"{duration} 時間" if duration and not duration.endswith("時間") else (duration or "未設定"))
        self.overview_label.setText(overview or "概要なし")
        self.synopsis_label.setText(synopsis or "あらすじなし")

        # 編集入力欄は、閲覧モード中または明示的なリセット要求（取消・アイテム切り替え等）時のみ上書き
        if (not self.is_edit_mode) or force_edit_inputs:
            self.edit_inputs["kana"].setText(kana)
            self.edit_inputs["title"].setText(title)
            self.edit_inputs["author"].setText(author)
            self.edit_inputs["system"].setText(system)
            self.edit_inputs["players"].setText(players)
            self.edit_inputs["duration"].setText(duration)
            self.url_edit.setText(url)
            self._on_url_edit_text_changed(url)
            self.overview_edit.setPlainText(overview)
            self.synopsis_edit.setPlainText(synopsis)

        # 情報元（ファイル/フォルダリンク、Webリンク、Notionリンク）の設定
        file_path = it[1] if len(it) > 1 and it[1] else ""
        has_file = False
        if file_path and not file_path.startswith("notion://"):
            clean_fp = file_path.strip().rstrip("/\\")
            base_name = os.path.basename(clean_fp) or clean_fp
            is_dir = os.path.isdir(file_path)
            icon = "📁" if is_dir else "📄"
            self.file_link_label.setText(f"{icon}  {base_name}")
            self.file_link_label.setToolTip(f"登録場所: {file_path}\nクリックしてフォルダを開きます")
            self.file_link_label.show()
            self.file_path_edit_lbl.setText(f"登録元: {file_path}")
            has_file = True
        else:
            self.file_link_label.hide()
            self.file_path_edit_lbl.setText("登録元: なし")

        # Notion取り込み／連携判定（誰とでも共有可能なグローバルリンク対応）
        notion_page_id = self.db.get_notion_page_id(self.item_id)
        notion_url = self.db.get_notion_url(self.item_id)
        is_notion = bool(notion_page_id) or bool(notion_url) or (file_path and file_path.startswith("notion://"))
        notion_deleted = not notion_page_id and bool(self.db.get_notion_deleted_page_id(self.item_id))
        if notion_deleted:
            # Notion 側でページが削除されたため連携を外した本（リンク先はもう無い）
            self.notion_link_label.hide()
            if hasattr(self, "notion_copy_btn"):
                self.notion_copy_btn.hide()
            self.notion_status_edit_lbl.setText("📓 Notion連携: Notion 側でページが削除されたため、連携を外しています")
            self.notion_status_edit_lbl.show()
        elif is_notion:
            if not notion_url:
                clean_nid = (notion_page_id or file_path.replace("notion://", "")).replace("-", "").strip()
                if clean_nid:
                    notion_url = f"https://www.notion.so/{clean_nid}"
            self.notion_link_label.setText("📓  Notion (共有リンク)")
            self.notion_link_label.setToolTip(f"Notion共有リンク: {notion_url}\nクリックして開きます（右クリックでコピー）")
            self.notion_link_label.show()
            if hasattr(self, "notion_copy_btn"):
                self.notion_copy_btn.show()
            self.notion_status_edit_lbl.setText("📓 Notion連携: 連携済み（Notionから取り込み・共有可能）")
            self.notion_status_edit_lbl.show()
        else:
            self.notion_link_label.hide()
            if hasattr(self, "notion_copy_btn"):
                self.notion_copy_btn.hide()
            self.notion_status_edit_lbl.hide()

        self._update_notion_sync_button()

        # 1. ファイルウィジェットの表示
        if has_file:
            self.file_item_widget.show()
        else:
            self.file_item_widget.hide()

        # 2. Web情報元ウィジェットの表示
        has_web = bool(url)
        if has_web:
            domain_label = app_settings.get_domain_label_for_url(url)
            if domain_label:
                self.url_label.setText(f"🔗  {domain_label}")
                self.view_add_domain_btn.hide()
            else:
                self.url_label.setText(f"🔗  {url}")
                # 未登録ドメインなら「＋ ドメイン登録」ボタンを表示
                self.view_add_domain_btn.show()
            self.url_label.setToolTip(f"URL: {url}\nクリックしてブラウザで開きます")
            self.url_label.show()
            self.web_item_widget.show()
        else:
            self.url_label.hide()
            self.view_add_domain_btn.hide()
            self.web_item_widget.hide()

        # 3. Notion情報元ウィジェットの表示（Notion 側で削除され連携を外した本は出さない）
        if is_notion and not notion_deleted:
            self.notion_item_widget.show()
        else:
            self.notion_item_widget.hide()

        # 4. 情報元が一切ない場合の未設定表示
        has_any = has_file or has_web or (is_notion and not notion_deleted)
        self.none_source_label.setVisible(not has_any)

        # タグの描画
        self._render_tags()

        # ウィンドウタイトルの更新
        win_title = f"異稿 - 紙裏 - あらすじ編集  ―  『{title or '無題'}』"
        self.setWindowTitle(win_title)
        if hasattr(self, "title_bar"):
            self.title_bar.setTitle(win_title)

        # セッション履歴（セッション記録）一覧を描画
        self._render_play_logs()

    def _center_on_parent_window(self, target_w=None, target_h=None):
        """現在のアプリ（メインウィンドウ）の中央に詳細ウィンドウを配置する"""
        if self.isMaximized():
            return

        w = target_w if target_w is not None else self.width()
        h = target_h if target_h is not None else self.height()
        w = max(700, w)
        h = max(500, h)

        parent = self.parent()
        if not parent or not parent.isVisible():
            for top in QApplication.topLevelWidgets():
                if top != self and top.isVisible() and top.__class__.__name__ == "MainWindow":
                    parent = top
                    break
        if not parent or not parent.isVisible():
            parent = QApplication.activeWindow()
            if parent == self:
                parent = None

        if parent and parent.isVisible():
            parent_geo = parent.frameGeometry()
            center_x = parent_geo.x() + (parent_geo.width() - w) // 2
            center_y = parent_geo.y() + (parent_geo.height() - h) // 2

            # 親ウィンドウが表示されているスクリーンを取得
            parent_window = parent.windowHandle()
            screen = parent_window.screen() if parent_window else (parent.screen() if hasattr(parent, "screen") else None)
            if not screen:
                screen = QApplication.primaryScreen()
            avail = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)

            # 画面端からはみ出さないよう補正（画面サイズ内に収まる場合のみクランプ）
            if w <= avail.width():
                applied_x = max(avail.x(), min(center_x, avail.right() - w))
            else:
                applied_x = center_x

            if h <= avail.height():
                applied_y = max(avail.y(), min(center_y, avail.bottom() - h))
            else:
                applied_y = center_y

            self.move(applied_x, applied_y)
        else:
            screen = QApplication.primaryScreen()
            avail = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
            applied_x = avail.x() + max(0, (avail.width() - w) // 2)
            applied_y = avail.y() + max(0, (avail.height() - h) // 2)
            self.move(applied_x, applied_y)

    def _init_window_geometry(self):
        """settings.ini から詳細画面のサイズ・最大化状態を読み出して適用し、位置はアプリ中央に配置"""
        self.setMinimumSize(700, 500)

        geom = app_settings.get_detail_window_geometry()
        w = geom.get("width")
        h = geom.get("height")
        is_max = geom.get("maximized", False)

        screen = QApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)

        if w and h:
            applied_w = max(700, int(w))
            applied_h = max(500, int(h))
            self.resize(applied_w, applied_h)
            self._center_on_parent_window(applied_w, applied_h)

            if is_max:
                self.showMaximized()
        else:
            # 初回デフォルトサイズ
            init_w = min(1020, max(700, int(avail.width() * 0.85)))
            init_h = min(890, max(500, int(avail.height() * 0.88)))
            self.resize(init_w, init_h)
            self._center_on_parent_window(init_w, init_h)
            self._save_geometry_to_ini()

    def _save_geometry_to_ini(self):
        """現在の詳細画面サイズ・位置・最大化状態を settings.ini に保存"""
        try:
            is_max = self.isMaximized()
            if is_max:
                geom = app_settings.get_detail_window_geometry()
                norm = self.normalGeometry()
                norm_w = norm.width() if norm.isValid() and norm.width() >= 700 else (geom.get("width") or 1020)
                norm_h = norm.height() if norm.isValid() and norm.height() >= 500 else (geom.get("height") or 890)
                norm_x = norm.x() if norm.isValid() else geom.get("x")
                norm_y = norm.y() if norm.isValid() else geom.get("y")
                app_settings.save_detail_window_geometry(
                    width=norm_w,
                    height=norm_h,
                    maximized=True,
                    x=norm_x,
                    y=norm_y,
                )
            else:
                w = max(700, self.width())
                h = max(500, self.height())
                pos = self.pos()
                app_settings.save_detail_window_geometry(
                    width=w,
                    height=h,
                    maximized=False,
                    x=pos.x(),
                    y=pos.y(),
                )
        except Exception:
            pass

    def nativeEvent(self, eventType, message):
        """Windows環境での滑らかなOSネイティブ・リサイズ処理（WM_NCHITTEST）"""
        if sys.platform == "win32" and eventType == b"windows_generic_MSG":
            import ctypes
            from ctypes import wintypes

            msg = wintypes.MSG.from_address(message.__int__())
            WM_NCHITTEST = 0x0084
            if msg.message == WM_NCHITTEST:
                if self.isMaximized():
                    return False, 0

                x = msg.lParam & 0xFFFF
                y = (msg.lParam >> 16) & 0xFFFF
                if x >= 0x8000:
                    x -= 0x10000
                if y >= 0x8000:
                    y -= 0x10000

                rect = self.frameGeometry()
                margin = 8  # リサイズ検知マージン (px)

                on_left = (rect.left() <= x < rect.left() + margin)
                on_right = (rect.right() - margin < x <= rect.right())
                on_top = (rect.top() <= y < rect.top() + margin)
                on_bottom = (rect.bottom() - margin < y <= rect.bottom())

                HTLEFT = 10
                HTRIGHT = 11
                HTTOP = 12
                HTTOPLEFT = 13
                HTTOPRIGHT = 14
                HTBOTTOM = 15
                HTBOTTOMLEFT = 16
                HTBOTTOMRIGHT = 17

                if on_top and on_left:
                    return True, HTTOPLEFT
                if on_top and on_right:
                    return True, HTTOPRIGHT
                if on_bottom and on_left:
                    return True, HTBOTTOMLEFT
                if on_bottom and on_right:
                    return True, HTBOTTOMRIGHT
                if on_left:
                    return True, HTLEFT
                if on_right:
                    return True, HTRIGHT
                if on_top:
                    return True, HTTOP
                if on_bottom:
                    return True, HTBOTTOM

        return super().nativeEvent(eventType, message)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 下部バーの幅は、ダイアログの大きさが変わった後のレイアウトで決まるため、その後で並べ直す
        QTimer.singleShot(0, self._layout_bottom_bar)
        if hasattr(self, "_save_geom_timer") and not self.isMaximized():
            self._save_geom_timer.start(400)

    def moveEvent(self, event):
        super().moveEvent(event)
        if hasattr(self, "_save_geom_timer") and not self.isMaximized():
            self._save_geom_timer.start(400)

    def closeEvent(self, event):
        if hasattr(self, "_save_geom_timer") and self._save_geom_timer.isActive():
            self._save_geom_timer.stop()
        self._save_geometry_to_ini()
        super().closeEvent(event)

    def exec(self):
        """親ウィンドウへのクリックを阻害しない非モーダル同期イベントループ"""
        from PySide6.QtCore import QEventLoop
        self.setWindowModality(Qt.NonModal)
        self.show()
        self._event_loop = QEventLoop()
        self._event_loop.exec()
        return self.result()

    def reject(self):
        if hasattr(self, "_save_geom_timer") and self._save_geom_timer.isActive():
            self._save_geom_timer.stop()
        self._save_geometry_to_ini()
        super().reject()
        if hasattr(self, "_event_loop") and self._event_loop and self._event_loop.isRunning():
            self._event_loop.quit()

    def accept(self):
        if hasattr(self, "_save_geom_timer") and self._save_geom_timer.isActive():
            self._save_geom_timer.stop()
        self._save_geometry_to_ini()
        super().accept()
        if hasattr(self, "_event_loop") and self._event_loop and self._event_loop.isRunning():
            self._event_loop.quit()

    def showEvent(self, event):
        super().showEvent(event)
        if not self.isMaximized():
            self._center_on_parent_window()
        QApplication.instance().installEventFilter(self)
        self._is_fully_shown = False
        QTimer.singleShot(250, lambda: setattr(self, "_is_fully_shown", True))

    def hideEvent(self, event):
        if hasattr(self, "_save_geom_timer") and self._save_geom_timer.isActive():
            self._save_geom_timer.stop()
        self._save_geometry_to_ini()
        QApplication.instance().removeEventFilter(self)
        if hasattr(self, "_event_loop") and self._event_loop and self._event_loop.isRunning():
            self._event_loop.quit()
        super().hideEvent(event)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange:
            if hasattr(self, "_save_geom_timer"):
                self._save_geom_timer.start(200)
            if hasattr(self, "title_bar") and hasattr(self.title_bar, "max_btn"):
                self.title_bar.max_btn.setText("❐" if self.isMaximized() else "□")
        elif event.type() == QEvent.ActivationChange:
            # 外部（デスクトップや別アプリ等）をクリックして非アクティブになった場合に閉じる
            if getattr(self, "_is_fully_shown", False) and self.isVisible() and not self.isActiveWindow():
                active_modal = QApplication.activeModalWidget()
                if active_modal and active_modal != self and (active_modal.parent() == self or self.isAncestorOf(active_modal)):
                    return
                active_popup = QApplication.activePopupWidget()
                if active_popup:
                    return
                focus_w = QApplication.focusWidget()
                if focus_w and (focus_w == self or self.isAncestorOf(focus_w)):
                    return
                self.reject()

    def eventFilter(self, obj, event):
        """詳細ウィンドウの枠外をクリックした場合、自動で閉じる"""
        if event.type() == QEvent.MouseButtonPress:
            pos = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
            # スクリーン絶対座標系でダイアログの矩形領域を計算
            dialog_rect = QRect(self.mapToGlobal(QPoint(0, 0)), self.size())
            if self.isVisible() and not dialog_rect.contains(pos):
                # このダイアログが開いた子ダイアログ（タグ編集やファイル選択等）のクリックは無視
                active_modal = QApplication.activeModalWidget()
                if active_modal and active_modal != self and (active_modal.parent() == self or self.isAncestorOf(active_modal)):
                    return super().eventFilter(obj, event)
                # ポップアップメニューのクリックも無視
                active_popup = QApplication.activePopupWidget()
                if active_popup:
                    return super().eventFilter(obj, event)
                self.reject()
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    def _update_fav_button_style(self):
        if self.is_favorite:
            self.fav_toggle_btn.setText("★  お気に入り")
            self.fav_toggle_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #2b2014;
                    color: #f1c40f;
                    border: 1px solid {Theme.BRASS_LIGHT};
                    border-radius: 2px;
                    padding: 2px 8px;
                    font-size: 11px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: #3d2d1b;
                    color: #ffffff;
                }}
            """)
        else:
            self.fav_toggle_btn.setText("☆  お気に入り追加")
            self.fav_toggle_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #17120e;
                    color: {Theme.TEXT_MUTED};
                    border: 1px solid #4a3a2a;
                    border-radius: 2px;
                    padding: 2px 8px;
                    font-size: 11px;
                }}
                QPushButton:hover {{
                    background-color: #251d16;
                    border: 1px solid {Theme.BRASS_BASE};
                    color: {Theme.BRASS_LIGHT};
                }}
            """)

    def _update_bm_button_style(self):
        if self.is_bookmarked:
            self.bm_toggle_btn.setText("🔖  しおり中")
            self.bm_toggle_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #2b2014;
                    color: {Theme.BRASS_LIGHT};
                    border: 1px solid {Theme.BRASS_LIGHT};
                    border-radius: 2px;
                    padding: 2px 8px;
                    font-size: 11px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: #3d2d1b;
                    color: #ffffff;
                }}
            """)
        else:
            self.bm_toggle_btn.setText("🔖  しおりを挟む")
            self.bm_toggle_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #17120e;
                    color: {Theme.TEXT_MUTED};
                    border: 1px solid #4a3a2a;
                    border-radius: 2px;
                    padding: 2px 8px;
                    font-size: 11px;
                }}
                QPushButton:hover {{
                    background-color: #251d16;
                    border: 1px solid {Theme.BRASS_BASE};
                    color: {Theme.BRASS_LIGHT};
                }}
            """)

    def _update_cover_badges(self):
        """表紙左上のお気に入り・しおりバッジの表示・位置更新"""
        self.fav_badge.setVisible(self.is_favorite)
        self.bm_badge.setVisible(self.is_bookmarked)
        x = 6
        if self.is_favorite:
            self.fav_badge.move(x, 6)
            self.fav_badge.raise_()
            x += 26
        if self.is_bookmarked:
            self.bm_badge.move(x, 6)
            self.bm_badge.raise_()

    def _toggle_favorite(self):
        """お気に入り状態の切り替え"""
        self.is_favorite = not self.is_favorite
        self.db.set_favorite(self.item_id, self.is_favorite)
        self._update_cover_badges()
        self._update_fav_button_style()
        self.item_updated.emit(self.item_id)

    def _toggle_bookmarked(self):
        """しおり状態の切り替え"""
        self.is_bookmarked = not self.is_bookmarked
        self.db.set_bookmarked(self.item_id, self.is_bookmarked)
        self._update_cover_badges()
        self._update_bm_button_style()
        self.item_updated.emit(self.item_id)

    def _update_navigation_buttons(self):
        """前後の書物めくりボタンと冊数表示の更新"""
        total = len(self.item_ids)
        curr = self.current_index + 1 if total > 0 else 0
        self.page_indicator.setText(f"―  {curr} / {total} 冊  ―")
        self.prev_btn.setEnabled(self.current_index > 0)
        self.next_btn.setEnabled(self.current_index < total - 1)

    def _go_prev(self):
        """前のシナリオへめくる"""
        if self.current_index > 0:
            self._navigate_to_index(self.current_index - 1)

    def _go_next(self):
        """次のシナリオへめくる"""
        if self.current_index < len(self.item_ids) - 1:
            self._navigate_to_index(self.current_index + 1)

    def _navigate_to_index(self, index):
        """指定インデックスのシナリオに移動して表示を更新"""
        if self.is_edit_mode:
            reply = QMessageBox.question(
                self,
                "編集の破棄確認",
                "編集中の内容は保存されていません。別の書物に移動しますか？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
            self._toggle_edit_mode()

        self.current_index = index
        self.item_id = self.item_ids[index]
        self.item_data = self.db.get_item(self.item_id)
        self.is_favorite = bool(self.db.get_favorite(self.item_id))
        self.is_bookmarked = bool(self.db.get_bookmarked(self.item_id))
        self._update_navigation_buttons()
        self._load_values(force_edit_inputs=True)
        self._update_fav_button_style()
        self._update_bm_button_style()
        self._update_cover_badges()

    def _load_shortcuts(self):
        """設定ファイルからショートカットキーを読み込み"""
        sc = app_settings.get_all_shortcuts()
        self.seq_prev = QKeySequence(sc.get("detail_prev", "Left"))
        self.seq_next = QKeySequence(sc.get("detail_next", "Right"))
        self.seq_fav = QKeySequence(sc.get("detail_favorite", "F"))
        self.seq_edit = QKeySequence(sc.get("detail_edit", "E"))
        self.seq_close = QKeySequence(sc.get("detail_close", "Esc"))

    def _matches_shortcut(self, event, target_seq):
        """キーイベントが指定されたQKeySequenceと一致するか判定"""
        if not target_seq or target_seq.isEmpty():
            return False
        try:
            seq = QKeySequence(event.keyCombination())
            if seq.matches(target_seq) == QKeySequence.ExactMatch:
                return True
        except Exception:
            pass
        # 文字キー（'F' や 'E' など単一文字）で修飾キーなしの場合のフォールバック
        if not event.modifiers() and event.text():
            if event.text().upper() == target_seq.toString().upper():
                return True
        return False

    def keyPressEvent(self, event):
        """設定欄で設定されたショートカットキーによる操作"""
        focus_w = self.focusWidget()
        is_typing = isinstance(focus_w, (QLineEdit, QTextEdit))

        # 閉じる / 取消（Esc または設定されたキー）
        if self._matches_shortcut(event, self.seq_close) or event.key() == Qt.Key_Escape:
            if self.is_edit_mode:
                self._on_cancel()
                event.accept()
                return
            else:
                self.close()
                event.accept()
                return

        # テキスト入力中でない場合、ページめくり・お気に入り・編集切り替え
        if not is_typing:
            if self._matches_shortcut(event, self.seq_prev) or event.key() in (Qt.Key_Left, Qt.Key_PageUp):
                self._go_prev()
                event.accept()
                return
            elif self._matches_shortcut(event, self.seq_next) or event.key() in (Qt.Key_Right, Qt.Key_PageDown):
                self._go_next()
                event.accept()
                return
            elif self._matches_shortcut(event, self.seq_fav):
                self._toggle_favorite()
                event.accept()
                return
            elif self._matches_shortcut(event, self.seq_edit):
                self._toggle_edit_mode()
                event.accept()
                return

        super().keyPressEvent(event)

    def _toggle_edit_mode(self):
        """閲覧モードと編集モードの切り替え"""
        self.is_edit_mode = not self.is_edit_mode

        # 表示/非表示の切り替え
        for k in self.view_labels:
            self.view_labels[k].setVisible(not self.is_edit_mode)
            self.edit_inputs[k].setVisible(self.is_edit_mode)

        self.source_view_widget.setVisible(not self.is_edit_mode)
        self.source_edit_widget.setVisible(self.is_edit_mode)

        self.overview_label.setVisible(not self.is_edit_mode)
        self.overview_edit.setVisible(self.is_edit_mode)

        self.synopsis_label.setVisible(not self.is_edit_mode)
        self.synopsis_edit.setVisible(self.is_edit_mode)

        # 左パネルの表紙変更・タグ編集ボタンの表示切替（編集画面に統一）
        self.change_cover_btn.setVisible(self.is_edit_mode)
        self.edit_tags_btn.setVisible(self.is_edit_mode)
        self.edit_global_tags_btn.setVisible(self.is_edit_mode)
        self.discard_btn.setVisible(self.is_edit_mode)

        self.edit_btn.setVisible(not self.is_edit_mode)
        self.save_btn.setVisible(self.is_edit_mode)
        self.cancel_btn.setVisible(self.is_edit_mode)
        self._update_notion_sync_button()

        # セッション履歴の追加・編集・削除は編集画面でだけ行う
        self.add_playlog_btn.setVisible(self.is_edit_mode)
        self._render_play_logs()

    def _layout_bottom_bar(self):
        """ページめくり（冊数の表示）を下部バー＝詳細画面の中央に置く。

        1 行に並べると中央に置けない幅（右側のボタンが多い編集画面など）のときは、
        ページめくりを 1 段上の行の中央に、ボタンをその下の行の右端に置く。
        """
        if not hasattr(self, "_bottom_grid"):
            return
        grid = self._bottom_grid
        spacing = self._action_spacing
        buttons = [b for b in (self.edit_btn, self.save_btn, self.cancel_btn) if not b.isHidden()]
        actions_w = sum(b.width() for b in buttons) + spacing * max(0, len(buttons) - 1)
        if not self.notion_sync_btn.isHidden():  # 「Notionと同期」は上の段に置く
            actions_w = max(actions_w, self.notion_sync_btn.width())
        nav_w = self._nav_box.sizeHint().width()
        margins = self._bottom_grid.contentsMargins()
        available = (self._bottom_bar.width() or self._bottom_bar.sizeHint().width()) - margins.left() - margins.right()
        two_rows = available < nav_w + 2 * (actions_w + spacing)

        if two_rows != self._bottom_two_rows:
            grid.removeWidget(self._nav_box)
            grid.removeWidget(self._action_box)
            if two_rows:
                grid.addWidget(self._nav_box, 0, 0, 1, 3, Qt.AlignHCenter)
                grid.addWidget(self._action_box, 1, 0, 1, 3, Qt.AlignRight)
            else:
                # ページめくりは「保存」「取消」の段（下の段）にそろえる
                grid.addWidget(self._nav_box, 0, 1, Qt.AlignHCenter | Qt.AlignBottom)
                grid.addWidget(self._action_box, 0, 2, Qt.AlignRight | Qt.AlignBottom)
            self._bottom_two_rows = two_rows
        # 1 行のときは左右の列を同じ幅にして、真ん中の列（ページめくり）を中央に保つ
        side = 0 if two_rows else actions_w
        for col in (0, 2):
            grid.setColumnMinimumWidth(col, side)
            grid.setColumnStretch(col, 0 if two_rows else 1)
        grid.setColumnStretch(1, 0)

    def _notion_page_id_for_sync(self):
        """この本が取り込まれた Notion のページ（無ければ空文字）"""
        page_id = self.db.get_notion_page_id(self.item_id) or ""
        if not page_id and self.db.get_notion_deleted_page_id(self.item_id):
            return ""  # Notion 側でページが削除され、連携を外した本
        if not page_id:
            it = self.db.get_item(self.item_id)
            file_path = (it[1] if it and len(it) > 1 else "") or ""
            if file_path.startswith("notion://"):
                page_id = file_path[len("notion://"):].strip()
        return page_id

    def _update_notion_sync_button(self):
        """「Notionと同期」は、Notion から取り込んだ本を編集しているときだけ出す"""
        if not hasattr(self, "notion_sync_btn"):
            return
        self.notion_sync_btn.setVisible(self.is_edit_mode and bool(self._notion_page_id_for_sync()))
        self._layout_bottom_bar()

    def _on_cancel(self):
        """編集の取消（破棄して閲覧モードへ戻す）"""
        self._toggle_edit_mode()
        self._load_values(force_edit_inputs=True)

    def _on_save(self):
        """全項目一括保存"""
        title = self.edit_inputs["title"].text().strip()
        kana = self.edit_inputs["kana"].text().strip()
        author = self.edit_inputs["author"].text().strip()
        system = self.edit_inputs["system"].text().strip()
        players = self.edit_inputs["players"].text().strip()
        duration = self.edit_inputs["duration"].text().strip()
        url = self.url_edit.text().strip()
        overview = self.overview_edit.toPlainText().strip()
        synopsis = self.synopsis_edit.toPlainText().strip()

        self.db.update_item_all(
            item_id=self.item_id,
            title=title,
            system_name=system,
            players_text=players,
            duration_text=duration,
            overview=overview,
            synopsis=synopsis,
            author=author,
            url=url,
            title_kana=kana,
        )

        if getattr(self, "_temp_thumb_bytes", None):
            self.db.update_item_cover(self.item_id, self._temp_thumb_bytes)
            self._temp_thumb_bytes = None

        self._toggle_edit_mode()
        self._load_values()
        self.item_updated.emit(self.item_id)
        QMessageBox.information(self, "保存完了", "シナリオ情報を更新しました。")

    def _on_file_link_clicked(self):
        """登録時のファイルまたはフォルダを開く"""
        it = self.db.get_item(self.item_id)
        if not it or not it[1]:
            QMessageBox.information(self, "案内", "登録時のファイルまたはフォルダ情報がありません。")
            return

        file_path = it[1].strip()
        norm_path = os.path.normpath(file_path)

        if not os.path.exists(norm_path):
            parent_dir = os.path.dirname(norm_path)
            if os.path.exists(parent_dir):
                QMessageBox.warning(
                    self,
                    "ファイル未発見",
                    f"登録時のファイルまたはフォルダが見つかりません:\n{norm_path}\n\n親フォルダを開きます。"
                )
                if sys.platform == "win32":
                    os.startfile(parent_dir)
                else:
                    QDesktopServices.openUrl(QUrl.fromLocalFile(parent_dir))
                return
            else:
                QMessageBox.warning(self, "エラー", f"指定されたパスが見つかりません:\n{norm_path}")
                return

        try:
            if os.path.isdir(norm_path):
                # フォルダであれば、そのフォルダを開いた状態にする
                if sys.platform == "win32":
                    os.startfile(norm_path)
                else:
                    QDesktopServices.openUrl(QUrl.fromLocalFile(norm_path))
            else:
                # ファイルなら、そのファイルが存在するフォルダを開く（Windowsではファイルを選択した状態で開く）
                if sys.platform == "win32":
                    subprocess.run(["explorer.exe", f"/select,{norm_path}"], shell=False)
                else:
                    parent_dir = os.path.dirname(norm_path)
                    QDesktopServices.openUrl(QUrl.fromLocalFile(parent_dir))
        except Exception as e:
            show_error(self, f"シナリオのフォルダを開く（{norm_path}）", "フォルダを開く際にエラーが発生しました", exc=e)

    def _on_url_clicked(self):
        raw_url = self.db.get_source_url(self.item_id)
        if not raw_url or not isinstance(raw_url, str):
            return
        url = raw_url.strip()
        # NULLバイトや制御文字、改行が含まれている場合は安全のため拒絶
        if any(c in url for c in "\x00\r\n\t") or any(ord(c) < 32 for c in url):
            QMessageBox.warning(self, "警告", "不正な制御文字が含まれるURLのため開くことができません。")
            return

        try:
            parsed = urllib.parse.urlparse(url)
            # http または https スキームのみ許可し、かつ有効なホスト名 (hostname) が必須
            if parsed.scheme.lower() in ("http", "https") and bool(parsed.hostname):
                QDesktopServices.openUrl(QUrl(url))
            else:
                QMessageBox.information(self, "案内", f"Webブラウザで開けない形式のURLです:\n{url}")
        except Exception as e:
            show_error(self, f"URL を開く（{url}）", "URL の検証中にエラーが発生しました", exc=e)

    def _get_effective_notion_url(self):
        """共有可能なNotionグローバルURLを取得する"""
        notion_url = self.db.get_notion_url(self.item_id)
        if notion_url and notion_url.strip():
            return notion_url.strip()

        page_id = self.db.get_notion_page_id(self.item_id)
        if not page_id:
            it = self.db.get_item(self.item_id)
            if it and it[1] and it[1].startswith("notion://"):
                page_id = it[1].replace("notion://", "").strip()

        if page_id:
            clean_id = page_id.replace("-", "").strip()
            return f"https://www.notion.so/{clean_id}"
        return ""

    def _on_notion_link_clicked(self, event=None):
        """Notionの該当ページを共有リンクとしてブラウザで開く（右クリック時はリンクをコピー）"""
        if event and hasattr(event, "button") and event.button() == Qt.RightButton:
            self._on_copy_notion_link()
            return

        notion_url = self._get_effective_notion_url()
        if not notion_url:
            QMessageBox.information(self, "案内", "Notionのリンク情報が見つかりません。")
            return

        try:
            QDesktopServices.openUrl(QUrl(notion_url))
        except Exception as e:
            show_error(self, f"Notion ページを開く（{notion_url}）", "Notion ページを開けませんでした", exc=e)

    def _on_copy_notion_link(self):
        """Notion共有リンクをクリップボードにコピーする"""
        notion_url = self._get_effective_notion_url()
        if not notion_url:
            QMessageBox.information(self, "案内", "Notionのリンク情報がありません。")
            return

        QApplication.clipboard().setText(notion_url)
        QMessageBox.information(self, "共有リンクをコピー", f"Notion共有リンクをクリップボードにコピーしました:\n{notion_url}")

    def _on_change_cover(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "表紙画像の選択", "", "画像ファイル (*.png *.jpg *.jpeg *.webp)"
        )
        if path and os.path.exists(path):
            with open(path, "rb") as f:
                data = f.read()
            self.db.update_item_cover(self.item_id, data)
            self._update_cover_preview(data)
            self.item_updated.emit(self.item_id)

    def _on_edit_tags(self):
        """ローカルタグ設定ダイアログを開く（自由タグの複数チェック・追加）"""
        self._edit_item_tags(is_global=False)

    def _on_edit_global_tags(self):
        """グローバルタグ設定ダイアログを開く（グローバルタグ一覧から選択）"""
        self._edit_item_tags(is_global=True)

    def _edit_item_tags(self, is_global):
        """別ウィンドウのタグ一覧で選んだ側（グローバル/ローカル）のタグだけを更新し、もう一方は維持する"""
        dlg = MultiTagEditDialog(self.item_id, self.db, self, is_global=is_global)
        if dlg.exec() == QDialog.Accepted:
            selected_ids = set(dlg.get_selected_tag_ids())
            other_ids = {t[0] for t in self.db.get_item_tags(self.item_id, is_global=not is_global)}
            self.db.set_item_tags(self.item_id, list(other_ids | selected_ids))
            self._render_tags()
            self.item_updated.emit(self.item_id)

    def _on_url_edit_text_changed(self, text):
        """URL入力欄の変更に応じて未登録ドメイン登録ボタンの表示を切り替え"""
        if not hasattr(self, "edit_add_domain_btn"):
            return
        url = (text or "").strip()
        if url and (url.startswith("http://") or url.startswith("https://")):
            domain_label = app_settings.get_domain_label_for_url(url)
            self.edit_add_domain_btn.setVisible(domain_label is None)
        else:
            self.edit_add_domain_btn.hide()

    def _on_fetch_web_info(self):
        """Web情報元URLからタイトル・作者・システム・人数・時間・あらすじ・表紙画像等のメタ情報を自動取得し、
        更新前の情報と比較して採用項目を選択・反映する。
        """
        url = self.url_edit.text().strip()
        if not url:
            QMessageBox.information(self, "案内", "情報元URLを入力してください。\n（例: BoothやTALTOの作品ページURL）")
            return

        self.fetch_web_btn.setEnabled(False)
        self.fetch_web_btn.setText("⏳ 取得中...")

        # 通信は別スレッドで行い、取得中も画面を操作できるようにする
        from core.web_extractor import WebScenarioExtractor
        target_id = self.item_id
        self._web_fetch_task = run_async(
            lambda: WebScenarioExtractor.extract_from_url(url, fetch_image=True),
            lambda data: self._apply_fetched_web_info(data, target_id),
            self._on_web_fetch_failed,
            owner=self,
        )

    def _reset_fetch_web_button(self):
        self._web_fetch_task = None
        self.fetch_web_btn.setEnabled(True)
        self.fetch_web_btn.setText("🌐  Web情報取得")

    def _on_web_fetch_failed(self, error):
        self._reset_fetch_web_button()
        show_error(self, f"Web から情報を取得する（{self.url_edit.text().strip()}）", "Web 情報の取得に失敗しました",
                   exc=error, title="取得エラー")

    def _apply_fetched_web_info(self, data, target_id=None):
        """取得した Web 情報を更新前の情報と比較し、選ばれた項目を入力欄に反映する"""
        if target_id is not None and target_id != self.item_id:
            # 取得中に別の書物へめくられた場合は反映しない
            self._reset_fetch_web_button()
            return
        try:
            # 現在の編集内容を収集
            current_it = self.db.get_item(self.item_id)
            curr_thumb = getattr(self, "_temp_thumb_bytes", None) or (current_it[8] if current_it else None)
            current_data = {
                "title": self.edit_inputs["title"].text().strip(),
                "author": self.edit_inputs["author"].text().strip(),
                "system": self.edit_inputs["system"].text().strip(),
                "players": self.edit_inputs["players"].text().strip(),
                "duration": self.edit_inputs["duration"].text().strip(),
                "overview": self.overview_edit.toPlainText().strip(),
                "synopsis": self.synopsis_edit.toPlainText().strip(),
                "thumbnail_bytes": curr_thumb,
            }

            # 比較・採否選択ダイアログを表示
            diff_dlg = WebInfoComparisonDialog(current_data, data, parent=self)
            if diff_dlg.exec() != QDialog.Accepted:
                return

            selected_fields = diff_dlg.get_selected_fields()
            if not selected_fields:
                QMessageBox.information(self, "案内", "反映対象として選択された項目はありませんでした。")
                return

            updated_fields = self._apply_selected_fetched_fields(data, selected_fields)

            if updated_fields:
                QMessageBox.information(
                    self,
                    "反映完了",
                    "選択された以下のWeb情報を入力欄に反映しました：\n・" + "\n・".join(updated_fields) + "\n\n※右下の［✓ 保存］ボタンを押すと変更が確定されます。",
                )
        except Exception as e:
            show_error(self, f"Web から取得した情報を反映する（{self.url_edit.text().strip()}）",
                       "Web 情報の反映に失敗しました", exc=e, title="取得エラー")
        finally:
            self._reset_fetch_web_button()

    def _on_discard_clicked(self):
        """シナリオを書架から破棄する。Notion から取り込んだ本は、Notion のページを残すか捨てるかも尋ねる"""
        if self._discard_task is not None:
            return
        item = self.db.get_item_detail_dict(self.item_id) or {}
        title = item.get("title") or "無題"
        page_id = self._notion_page_id_for_sync()

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("シナリオの破棄")
        text = f"『{title}』を破棄しますか？\nセッション履歴（通過記録）などの記録も、手元から消えます。\n（元のPDFなどのファイル自体は削除されません）"
        if page_id:
            text += "\n\nこの本は Notion から取り込まれています。Notion のページをどうしますか？"
        box.setText(text)
        local_btn = box.addButton("手元だけ破棄" if page_id else "破棄する", QMessageBox.AcceptRole)
        trash_btn = None
        if page_id:
            trash_btn = box.addButton("Notion のページもゴミ箱へ", QMessageBox.DestructiveRole)
        cancel_btn = box.addButton("キャンセル", QMessageBox.RejectRole)
        box.setDefaultButton(cancel_btn)
        box.setEscapeButton(cancel_btn)
        box.exec()
        clicked = box.clickedButton()

        if clicked is local_btn:
            # 手元だけ破棄した本は、次の同調で Notion から取り込み直さない
            self._finish_discard(self.item_id, ignore_page=page_id or None)
        elif trash_btn is not None and clicked is trash_btn:
            from .notion_sync_dialog import open_notion_connection

            def trash():
                client = open_notion_connection()[0]
                client.trash_page(page_id)

            target_id = self.item_id
            self.discard_btn.setEnabled(False)
            self.discard_btn.setText("⏳ 破棄中...")
            self._discard_task = run_async(
                trash,
                lambda _r: self._finish_discard(target_id),
                lambda error: self._on_discard_failed(error, title),
                owner=self,
            )

    def _on_discard_failed(self, error, title):
        self._discard_task = None
        self.discard_btn.setEnabled(True)
        self.discard_btn.setText("🗑  このシナリオを破棄")
        show_error(self, f"Notion のページをゴミ箱へ移す（『{title}』）",
                   "Notion のページを削除できなかったため、シナリオは破棄していません",
                   exc=error, title="Notion同期エラー")

    def _finish_discard(self, item_id, ignore_page=None):
        self._discard_task = None
        try:
            self.db.delete_item(item_id, ignore_notion_page=ignore_page)
        except Exception as e:
            show_error(self, "シナリオを破棄する", "シナリオを破棄できませんでした", exc=e)
            return
        self.item_deleted.emit(item_id)
        self.accept()

    def _on_notion_sync_clicked(self):
        """Notion から最新の内容を取得し、手元と比べて反映する項目を選んでもらう（通信は別スレッド）"""
        page_id = self._notion_page_id_for_sync()
        if not page_id or self._notion_fetch_task is not None:
            return
        from .notion_sync_dialog import fetch_notion_page

        self.notion_sync_btn.setEnabled(False)
        self.notion_sync_btn.setText("⏳ 取得中...")
        target_id = self.item_id
        self._notion_fetch_task = run_async(
            lambda: fetch_notion_page(page_id),
            lambda fetched: self._apply_notion_page(fetched, target_id, page_id),
            lambda error: self._on_notion_fetch_failed(error, target_id),
            owner=self,
        )

    def _reset_notion_sync_button(self):
        self._notion_fetch_task = None
        self.notion_sync_btn.setEnabled(True)
        self.notion_sync_btn.setText("📓  Notionと同期")

    def _on_notion_fetch_failed(self, error, target_id):
        self._reset_notion_sync_button()
        title = self.db.get_item_detail_dict(target_id).get("title") if target_id else ""
        show_error(self, f"Notion から情報を取得する（『{title or '無題'}』）", "Notion からの取得に失敗しました",
                   exc=error, title="Notion同期エラー")

    def _apply_notion_page(self, fetched, target_id, page_id):
        """Notion から取得した内容を手元と比べ、選ばれた項目を入力欄に反映する"""
        try:
            if target_id != self.item_id or not self.is_edit_mode:
                return  # 取得中に別の書物へめくられた・編集をやめた場合は反映しない
            values = dict(fetched.get("values") or {})
            notion_sync.keep_local_system(values, self.edit_inputs["system"].text())
            notion_sync.keep_local_players(values, self.edit_inputs["players"].text())
            notion_sync.keep_local_duration(values, self.edit_inputs["duration"].text())

            # 通過記録は Notion から読み込むだけの情報なので、比べずにそのまま取り込む
            play_log_changed = False
            if "play_log" in values:
                play_log_changed = self.db.apply_notion_play_log(self.item_id, page_id, values["play_log"])
                if play_log_changed:
                    self._render_play_logs()
                    self.item_updated.emit(self.item_id)

            current_it = self.db.get_item(self.item_id)
            curr_thumb = getattr(self, "_temp_thumb_bytes", None) or (current_it[8] if current_it else None)
            current_data = {
                "title": self.edit_inputs["title"].text().strip(),
                "author": self.edit_inputs["author"].text().strip(),
                "system": self.edit_inputs["system"].text().strip(),
                "players": self.edit_inputs["players"].text().strip(),
                "duration": self.edit_inputs["duration"].text().strip(),
                "overview": self.overview_edit.toPlainText().strip(),
                "synopsis": self.synopsis_edit.toPlainText().strip(),
                "tags": [t[1] for t in self.db.get_item_tags(self.item_id)],
                "thumbnail_bytes": curr_thumb,
            }
            notion_data = {
                "title": values.get("title") or "",
                "author": values.get("author") or "",
                "system": values.get("system_name") or "",
                "players": values.get("players_text") or "",
                "duration": values.get("duration_text") or "",
                "overview": values.get("overview") or "",
                "synopsis": values.get("synopsis") or "",
                "image_bytes": fetched.get("image_bytes"),
            }
            if values.get("tags") is not None:
                notion_data["tags"] = list(values.get("tags") or [])

            # 情報元の URL は比較画面に無いため、手元が空のときだけ Notion の値を入れる
            filled = []
            notion_source = (values.get("source_url") or "").strip()
            if notion_source and not self.url_edit.text().strip():
                self.url_edit.setText(notion_source)
                filled.append("情報元の URL")

            if not self._differs_from_notion(current_data, notion_data):
                lines = ["手元の内容は Notion と同じです。"]
                if filled:
                    lines.append("空欄だった次の項目を入力欄に入れました：\n・" + "\n・".join(filled))
                if play_log_changed:
                    lines.append("Notion の通過記録をセッション履歴に取り込みました。")
                QMessageBox.information(self, "Notionと同期", "\n\n".join(lines))
                return

            diff_dlg = WebInfoComparisonDialog(current_data, notion_data, parent=self, source_name="Notion")
            if diff_dlg.exec() != QDialog.Accepted:
                return
            selected_fields = diff_dlg.get_selected_fields()
            updated_fields = self._apply_selected_fetched_fields(notion_data, selected_fields) + filled

            if "tags" in selected_fields and "tags" in notion_data:
                # タグは入力欄が無いため、ここで確定する（同調で取り込むときと同じく Notion のタグにそろえる）
                self.db.set_tags_from_notion(self.item_id, notion_data["tags"])
                self._render_tags()
                self.item_updated.emit(self.item_id)

            lines = []
            if updated_fields:
                lines.append("Notion の次の情報を入力欄に反映しました：\n・" + "\n・".join(updated_fields)
                             + "\n\n※右下の［💾 保存］ボタンを押すと変更が確定されます。")
            if "tags" in selected_fields and "tags" in notion_data:
                lines.append("タグを Notion のタグにそろえました（保存しなくても反映済みです）。")
            if play_log_changed:
                lines.append("Notion の通過記録をセッション履歴に取り込みました。")
            if lines:
                QMessageBox.information(self, "Notionと同期", "\n\n".join(lines))
            elif not selected_fields:
                QMessageBox.information(self, "案内", "反映対象として選択された項目はありませんでした。")
        except Exception as e:
            show_error(self, f"Notion から取得した情報を反映する（ページ {page_id}）", "Notion の情報の反映に失敗しました",
                       exc=e, title="Notion同期エラー")
        finally:
            self._reset_notion_sync_button()

    @staticmethod
    def _differs_from_notion(current, notion):
        for key in ("title", "author", "system", "players", "duration", "overview", "synopsis"):
            if (notion.get(key) or "").strip() and (current.get(key) or "").strip() != (notion.get(key) or "").strip():
                return True
        if "tags" in notion and set(current.get("tags") or []) != set(notion.get("tags") or []):
            return True
        new_cover = notion.get("image_bytes")
        return bool(new_cover and new_cover != current.get("thumbnail_bytes"))

    def _apply_selected_fetched_fields(self, data, selected_fields):
        """比較画面で選ばれた項目を入力欄（表紙はプレビュー）に反映し、反映した項目名の一覧を返す"""
        updated_fields = []
        for key, label in (("title", "タイトル"), ("author", "作者"), ("system", "システム"),
                           ("players", "プレイ人数"), ("duration", "プレイ時間")):
            if key in selected_fields and data.get(key):
                self.edit_inputs[key].setText(data[key])
                updated_fields.append(label)

        if "overview" in selected_fields and data.get("overview"):
            self.overview_edit.setPlainText(data["overview"])
            updated_fields.append("概要")

        if "synopsis" in selected_fields and data.get("synopsis"):
            self.synopsis_edit.setPlainText(data["synopsis"])
            updated_fields.append("あらすじ")

        if "cover" in selected_fields and data.get("image_bytes"):
            pix = QPixmap()
            if pix.loadFromData(QByteArray(data["image_bytes"])) and not pix.isNull():
                self._temp_thumb_bytes = data["image_bytes"]
                self.cover_label.setPixmap(pix.scaled(262, 177, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                updated_fields.append("表紙画像")
        return updated_fields

    def _on_add_domain_clicked(self, target_url=""):
        """現在のURLからドメイン表示設定ダイアログを開いて登録"""
        url = target_url or self.url_edit.text().strip() or self.db.get_source_url(self.item_id) or ""
        clean_d = app_settings.clean_domain(url)
        if not clean_d:
            QMessageBox.information(self, "案内", "有効なURLが入力されていません。")
            return

        from .settings_dialog import DomainEditDialog
        dlg = DomainEditDialog(domain=clean_d, label="", parent=self)
        if dlg.exec():
            mappings = app_settings.get_domain_mappings()
            mappings[dlg.result_domain] = dlg.result_label
            app_settings.save_domain_mappings(mappings)
            self._load_values()
            QMessageBox.information(
                self,
                "登録完了",
                f"ドメイン「{dlg.result_domain}」を表示名「{dlg.result_label}」として登録しました。",
            )

    # -------------------------------------------------------------------------
    # セッション履歴（プレイ履歴・セッション記録）
    # -------------------------------------------------------------------------
    def _render_play_logs(self):
        """セッション履歴一覧を描画"""
        if not hasattr(self, "playlog_layout"):
            return

        while self.playlog_layout.count():
            item = self.playlog_layout.takeAt(0)
            if item.widget():
                item.widget().hide()  # 実際に消えるまでの間も表示に残らないように
                item.widget().deleteLater()

        logs = self.db.get_play_logs(self.item_id)
        if not logs:
            hint = "「＋ 記録を追加」" if self.is_edit_mode else "「✎ 編集」"
            empty_lbl = QLabel(f"（まだセッション履歴はありません。{hint}からセッションの思い出を記録できます）")
            empty_lbl.setWordWrap(True)
            empty_lbl.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 11px; font-style: italic; padding: 4px 0;")
            self.playlog_layout.addWidget(empty_lbl)
            return

        for log in logs:
            self.playlog_layout.addWidget(self._make_play_log_card(log))

    @staticmethod
    def _play_log_badge(text, color, background="transparent", bold=False):
        badge = QLabel(f" {text} ")
        badge.setStyleSheet(f"""
            background-color: {background};
            color: {color};
            border: 1px solid {color};
            border-radius: 2px;
            font-size: 10px;
            {"font-weight: bold;" if bold else ""}
            padding: 1px 4px;
        """)
        return badge

    def _make_play_log_card(self, log):
        """セッション履歴 1 件分のカード。見出し（日付・役割・結果）の下に、項目を 1 行ずつ並べる"""
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #16120e;
                border: 1px solid #3d2f21;
                border-radius: 4px;
            }
        """)
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(10, 8, 10, 8)
        c_layout.setSpacing(4)

        # 見出し: 日付・役割バッジ・結果バッジ・Notion 印（編集画面では編集・削除ボタン）
        header = QHBoxLayout()
        header.setSpacing(8)

        date_lbl = QLabel(f"📅  {log.get('session_date') or '日付未設定'}")
        date_lbl.setStyleSheet(f"color: {Theme.BRASS_LIGHT}; font-weight: bold; font-size: 12px; border: none;")
        header.addWidget(date_lbl)

        role = log.get("role") or ""
        if role:
            is_gm = "GM" in role or "KP" in role
            header.addWidget(self._play_log_badge(
                role, Theme.BRASS_LIGHT if is_gm else "#64b5f6", "#2b2014" if is_gm else "#152238"))

        result = log.get("result") or ""
        if result:
            if "生還" in result or "True" in result:
                res_color, res_bg = "#69db7c", "#1b3320"
            elif "ロスト" in result:
                res_color, res_bg = "#ff6b6b", "#3a1818"
            else:
                res_color, res_bg = "#e5c07b", "#2b2014"
            header.addWidget(self._play_log_badge(result, res_color, res_bg, bold=True))

        if log.get("notion_page_id"):
            n_badge = self._play_log_badge("Notion", "#9e9e9e")
            n_badge.setToolTip("Notion から取り込んだ記録です（Notion 側が変わると次の同調で更新されます）")
            header.addWidget(n_badge)

        header.addStretch()

        if self.is_edit_mode:
            edit_btn = QPushButton("✎ 編集")
            edit_btn.setFixedSize(58, 24)
            edit_btn.setCursor(Qt.PointingHandCursor)
            edit_btn.setToolTip("このセッション履歴を編集")
            edit_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #221a14;
                    color: {Theme.BRASS_LIGHT};
                    border: 1px solid #4a3a2a;
                    border-radius: 2px;
                    font-size: 11px;
                    padding: 0px;
                }}
                QPushButton:hover {{
                    border: 1px solid {Theme.BRASS_LIGHT};
                    color: #ffffff;
                }}
            """)
            edit_btn.clicked.connect(lambda _, l=log: self._on_edit_play_log(l))
            header.addWidget(edit_btn)

            del_btn = QPushButton("✕ 削除")
            del_btn.setFixedSize(58, 24)
            del_btn.setCursor(Qt.PointingHandCursor)
            del_btn.setToolTip("このセッション履歴を削除")
            del_btn.setStyleSheet("""
                QPushButton {
                    background-color: #2a1515;
                    color: #e57373;
                    border: 1px solid #5a2525;
                    border-radius: 2px;
                    font-size: 11px;
                    padding: 0px;
                }
                QPushButton:hover {
                    border: 1px solid #d32f2f;
                    color: #ffffff;
                }
            """)
            del_btn.clicked.connect(lambda _, lid=log["id"]: self._on_delete_play_log(lid))
            header.addWidget(del_btn)

        c_layout.addLayout(header)

        # 項目は 1 行ずつ（長い名前や URL でもカードの幅を広げず、折り返して表示する）
        def add_line(text, color="#d8ccb8", rich=False):
            lbl = QLabel(text)
            lbl.setWordWrap(True)
            lbl.setTextFormat(Qt.RichText if rich else Qt.PlainText)
            lbl.setOpenExternalLinks(rich)
            lbl.setTextInteractionFlags(Qt.TextBrowserInteraction if rich else Qt.TextSelectableByMouse)
            lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            lbl.setStyleSheet(f"color: {color}; font-size: 12px; border: none;")
            c_layout.addWidget(lbl)
            return lbl

        if log.get("character_name"):
            add_line(f"🧙  PC: {log['character_name']}", "#ffffff")
        if log.get("gm"):
            add_line(f"🎲  GM: {log['gm']}")
        if log.get("party_members"):
            add_line(f"👥  卓メンバー: {log['party_members']}")

        sheet_url = log.get("sheet_url") or ""
        if sheet_url:
            if sheet_url.startswith(("http://", "https://")):
                shown = sheet_url if len(sheet_url) <= 60 else sheet_url[:57] + "…"
                link = add_line(
                    f'📜  キャラクターシート: <a href="{html.escape(sheet_url, quote=True)}" '
                    f'style="color: {Theme.BRASS_LIGHT};">{html.escape(shown)}</a>',
                    rich=True,
                )
                link.setToolTip(sheet_url)
            else:
                add_line(f"📜  キャラクターシート: {sheet_url}")

        memo = log.get("memo") or ""
        if memo:
            memo_lbl = add_line(memo, "#dcd0bd")
            memo_lbl.setStyleSheet("color: #dcd0bd; font-size: 12px; line-height: 1.5; border: none; padding-top: 4px;")
        return card

    def _on_add_play_log(self):
        """新しいセッション履歴（セッション記録）を追加"""
        from .play_log_dialog import PlayLogEditDialog
        dlg = PlayLogEditDialog(parent=self)
        if dlg.exec():
            d = dlg.result_data
            self.db.add_play_log(
                item_id=self.item_id,
                session_date=d["session_date"],
                role=d["role"],
                party_members=d["party_members"],
                character_name=d["character_name"],
                result=d["result"],
                memo=d["memo"],
                gm=d.get("gm", ""),
                sheet_url=d.get("sheet_url", ""),
            )
            # 自動で「通過済み」タグを付与
            self.db.toggle_item_tag(self.item_id, "通過済み", enabled=True)
            self._load_values()
            self.item_updated.emit(self.item_id)
            QMessageBox.information(self, "記録完了", "セッション履歴を記録しました。\n（※ シナリオに『通過済み』タグを付与しました）")

    def _on_edit_play_log(self, log_dict):
        """既存のセッション履歴を編集"""
        from .play_log_dialog import PlayLogEditDialog
        dlg = PlayLogEditDialog(log_data=log_dict, parent=self)
        if dlg.exec():
            d = dlg.result_data
            self.db.update_play_log(
                log_id=log_dict["id"],
                session_date=d["session_date"],
                role=d["role"],
                party_members=d["party_members"],
                character_name=d["character_name"],
                result=d["result"],
                memo=d["memo"],
                gm=d.get("gm"),
                sheet_url=d.get("sheet_url"),
            )
            self._render_play_logs()
            self.item_updated.emit(self.item_id)

    def _on_delete_play_log(self, log_id):
        """セッション履歴を削除"""
        reply = QMessageBox.question(
            self,
            "削除確認",
            "このセッション履歴を削除しますか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.db.delete_play_log(log_id)
            self._render_play_logs()
            self.item_updated.emit(self.item_id)

