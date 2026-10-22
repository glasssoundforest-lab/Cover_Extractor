"""設定ダイアログ (gui_qt/dialogs/settings_dialog.py)

タグ一覧管理（名前・色変更）、ショートカットキー設定、Notion連携設定を提供する西洋古書調ダイアログ。
"""

import os
import re
from PySide6.QtCore import Qt, Signal, QPoint, QUrl
from PySide6.QtGui import QKeySequence, QColor, QPixmap, QPainter, QPen, QBrush, QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QMessageBox,
    QFrame,
    QTabWidget,
    QWidget,
    QKeySequenceEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QColorDialog,
    QSlider,
    QCheckBox,
    QDoubleSpinBox,
    QSpinBox,
    QFileDialog,
)

from ..theme import Theme
from ..components.ornate import OrnateFrame, OrnateDivider, make_fleur_pixmap, PillTag
from ..components.ornate_title_bar import OrnateTitleBar
import app_settings


def make_color_circle_pixmap(color_hex, size=14):
    """西洋アンティーク調の真鍮枠付きカラーサークルPixmap"""
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(Theme.BRASS_LIGHT), 1))
    p.setBrush(QBrush(QColor(color_hex or "#546e7a")))
    p.drawEllipse(1, 1, size - 2, size - 2)
    p.end()
    return pix


def extract_notion_id_from_url(url_or_text: str) -> str:
    """NotionのページURLまたはテキストから32桁のデータベースIDを抽出・生成する"""
    text = (url_or_text or "").strip()
    if not text:
        return ""

    # すでにハイフンなしの32文字16進数の場合
    clean_no_hyphen = text.replace("-", "")
    if re.fullmatch(r"[0-9a-fA-F]{32}", clean_no_hyphen):
        return clean_no_hyphen.lower()

    # URLからクエリパラメータ (?v=...) やハッシュ (#...) を分離
    clean_url = text.split("?")[0].split("#")[0].rstrip("/")

    # パス末尾（最後のスラッシュの後）を取得
    last_segment = clean_url.split("/")[-1] if "/" in clean_url else clean_url

    # 1. ハイフン区切りのUUID形式 (8-4-4-4-12) が含まれている場合
    uuid_match = re.search(
        r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})",
        last_segment,
    )
    if uuid_match:
        return uuid_match.group(1).replace("-", "").lower()

    # 2. ハイフンで区切られている場合の最後のトークンが32桁HEXかチェック
    # 例: "TRPG-Archive-8f2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e"
    if "-" in last_segment:
        candidate = last_segment.split("-")[-1]
        if len(candidate) == 32 and re.fullmatch(r"[0-9a-fA-F]{32}", candidate):
            return candidate.lower()

    # 3. セグメントの末尾32文字が16進数かチェック
    if len(last_segment) >= 32:
        candidate = last_segment[-32:]
        if re.fullmatch(r"[0-9a-fA-F]{32}", candidate):
            return candidate.lower()

    # 4. セグメントからハイフンを除去した文字列の末尾32文字をチェック
    seg_clean = last_segment.replace("-", "")
    if len(seg_clean) >= 32:
        candidate = seg_clean[-32:]
        if re.fullmatch(r"[0-9a-fA-F]{32}", candidate):
            return candidate.lower()

    # 5. 全体からハイフンなし32文字HEXを検索（末尾を優先）
    all_hex = re.findall(r"([0-9a-fA-F]{32})", text.replace("-", ""))
    if all_hex:
        return all_hex[-1].lower()

    return text


class TagEditDialog(QDialog):
    """西洋古書調のしおり・タグ編集ダイアログ（タグ名・色変更、自由調色、グローバル/ローカル切り替え）"""
    def __init__(self, tag_id, current_name, current_color, db, is_global=None, parent=None):
        super().__init__(parent)
        self.tag_id = tag_id
        self.db = db
        self.selected_color = (current_color or "#546e7a").lower()
        if is_global is None and self.db:
            tag_row = self.db.get_tag_by_name(current_name)
            self.is_global = bool(tag_row[3]) if tag_row and len(tag_row) > 3 else False
        else:
            self.is_global = bool(is_global)
        self._updating = False

        self.setWindowTitle("しおり・タグの編集")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.resize(470, 560)
        self.setStyleSheet(Theme.get_application_stylesheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.frame = OrnateFrame(self, bracket_size=14, bg_color="#181310")
        layout.addWidget(self.frame)

        f_layout = QVBoxLayout(self.frame)
        f_layout.setContentsMargins(0, 0, 0, 14)
        f_layout.setSpacing(10)

        # 画面デザイン一体型タイトルバー
        self.title_bar = OrnateTitleBar("しおり・タグの編集", parent=self, show_close=True)
        f_layout.addWidget(self.title_bar)

        content_widget = QWidget()
        c_main_layout = QVBoxLayout(content_widget)
        c_main_layout.setContentsMargins(16, 4, 16, 0)
        c_main_layout.setSpacing(10)
        f_layout.addWidget(content_widget)

        # 1. タグ名入力
        name_lbl = QLabel("タグ名:")
        name_lbl.setStyleSheet(f"color: {Theme.TEXT_WHITE}; font-size: 12px; font-weight: bold;")
        c_main_layout.addWidget(name_lbl)

        self.name_edit = QLineEdit(current_name)
        self.name_edit.setFixedHeight(28)
        self.name_edit.setStyleSheet(f"""
            QLineEdit {{
                background-color: #191410;
                color: #ffffff;
                border: 1px solid {Theme.BRASS_BASE};
                border-radius: 2px;
                padding: 4px 8px;
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border: 1px solid {Theme.BRASS_LIGHT};
            }}
        """)
        self.name_edit.textChanged.connect(self._update_preview)
        c_main_layout.addWidget(self.name_edit)

        # グローバルタグ設定チェックボックス
        self.global_check = QCheckBox("🌐  グローバルタグにする（シナリオ右クリックメニューに表示）")
        self.global_check.setChecked(self.is_global)
        self.global_check.setCursor(Qt.PointingHandCursor)
        self.global_check.setStyleSheet(f"""
            QCheckBox {{
                color: {Theme.TEXT_WHITE};
                font-size: 11px;
                font-family: {Theme.FONT_SERIF};
                spacing: 8px;
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
            QCheckBox::indicator:hover {{
                border: 1px solid {Theme.BRASS_LIGHT};
                background-color: #241c14;
            }}
            QCheckBox::indicator:checked {{
                background-color: {Theme.BRASS_BASE};
            }}
        """)
        c_main_layout.addWidget(self.global_check)

        # 2. 厳選プリセットパレット (10色)
        color_lbl = QLabel("推薦パレット (10色):")
        color_lbl.setStyleSheet(f"color: {Theme.TEXT_WHITE}; font-size: 12px; font-weight: bold;")
        c_main_layout.addWidget(color_lbl)

        palette_grid = QGridLayout()
        palette_grid.setSpacing(8)

        self.PRESET_COLORS = [
            ("#1b5e20", "深緑 (クトゥルフ神話・秘術)"),
            ("#6a1b9a", "深紫 (マーダーミステリー・幻惑)"),
            ("#9e2a2b", "深紅 (通過済み・封蝋)"),
            ("#1565c0", "青藍 (未通過・夜空)"),
            ("#b3882a", "真鍮金 (GM可・古金)"),
            ("#b8621b", "琥珀 (アンバー・蜜蝋)"),
            ("#795548", "セピア (羊皮紙・古書)"),
            ("#004d40", "鉄緑 (青銅・ティール)"),
            ("#283593", "紺青 (インディゴ・星辰)"),
            ("#546e7a", "蒼灰 (スレート・石造)"),
        ]

        self.color_buttons = []
        for i, (c_hex, c_desc) in enumerate(self.PRESET_COLORS):
            btn = QPushButton()
            btn.setFixedSize(30, 30)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(c_desc)
            btn.clicked.connect(lambda _, c=c_hex: self._select_preset_color(c))
            self.color_buttons.append((btn, c_hex.lower()))
            palette_grid.addWidget(btn, i // 5, i % 5)

        c_main_layout.addLayout(palette_grid)

        # 3. 自由に色が作れる領域（自由調色パレット）
        custom_box = QFrame()
        custom_box.setStyleSheet(f"""
            QFrame {{
                background-color: #140f0c;
                border: 1px solid #3d2f21;
                border-radius: 4px;
                padding: 6px;
            }}
        """)
        c_layout = QVBoxLayout(custom_box)
        c_layout.setContentsMargins(10, 8, 10, 8)
        c_layout.setSpacing(6)

        c_title = QLabel("🎨  自由調色 (カスタムカラー作成)")
        c_title.setStyleSheet(f"color: {Theme.BRASS_LIGHT}; font-size: 11px; font-weight: bold; border: none;")
        c_layout.addWidget(c_title)

        slider_qss = f"""
            QSlider::groove:horizontal {{
                border: 1px solid #3d2f21;
                height: 4px;
                background: #191410;
                border-radius: 2px;
            }}
            QSlider::sub-page:horizontal {{
                background: #4a3825;
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {Theme.BRASS_BASE};
                border: 1px solid {Theme.BRASS_LIGHT};
                width: 12px;
                margin-top: -4px;
                margin-bottom: -4px;
                border-radius: 6px;
            }}
            QSlider::handle:horizontal:hover {{
                background: {Theme.BRASS_LIGHT};
                border: 1px solid #ffffff;
            }}
        """

        # R (赤)
        r_row = QHBoxLayout()
        r_lbl = QLabel("R")
        r_lbl.setStyleSheet("color: #ff6b6b; font-weight: bold; font-size: 11px; background: transparent; border: none; padding: 0;")
        r_lbl.setFixedWidth(18)
        r_lbl.setAlignment(Qt.AlignCenter)
        self.r_slider = QSlider(Qt.Horizontal)
        self.r_slider.setRange(0, 255)
        self.r_slider.setStyleSheet(slider_qss)
        self.r_val = QLabel("0")
        self.r_val.setFixedWidth(34)
        self.r_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.r_val.setStyleSheet("color: #dcd0bd; font-size: 11px; background: transparent; border: none;")
        self.r_slider.valueChanged.connect(self._on_slider_changed)
        r_row.addWidget(r_lbl)
        r_row.addWidget(self.r_slider)
        r_row.addWidget(self.r_val)
        c_layout.addLayout(r_row)

        # G (緑)
        g_row = QHBoxLayout()
        g_lbl = QLabel("G")
        g_lbl.setStyleSheet("color: #69db7c; font-weight: bold; font-size: 11px; background: transparent; border: none; padding: 0;")
        g_lbl.setFixedWidth(18)
        g_lbl.setAlignment(Qt.AlignCenter)
        self.g_slider = QSlider(Qt.Horizontal)
        self.g_slider.setRange(0, 255)
        self.g_slider.setStyleSheet(slider_qss)
        self.g_val = QLabel("0")
        self.g_val.setFixedWidth(34)
        self.g_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.g_val.setStyleSheet("color: #dcd0bd; font-size: 11px; background: transparent; border: none;")
        self.g_slider.valueChanged.connect(self._on_slider_changed)
        g_row.addWidget(g_lbl)
        g_row.addWidget(self.g_slider)
        g_row.addWidget(self.g_val)
        c_layout.addLayout(g_row)

        # B (青)
        b_row = QHBoxLayout()
        b_lbl = QLabel("B")
        b_lbl.setStyleSheet("color: #4dabf7; font-weight: bold; font-size: 11px; background: transparent; border: none; padding: 0;")
        b_lbl.setFixedWidth(18)
        b_lbl.setAlignment(Qt.AlignCenter)
        self.b_slider = QSlider(Qt.Horizontal)
        self.b_slider.setRange(0, 255)
        self.b_slider.setStyleSheet(slider_qss)
        self.b_val = QLabel("0")
        self.b_val.setFixedWidth(34)
        self.b_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.b_val.setStyleSheet("color: #dcd0bd; font-size: 11px; background: transparent; border: none;")
        self.b_slider.valueChanged.connect(self._on_slider_changed)
        b_row.addWidget(b_lbl)
        b_row.addWidget(self.b_slider)
        b_row.addWidget(self.b_val)
        c_layout.addLayout(b_row)

        # 調色詳細バー (スウォッチ + HEX入力 + 詳細ピッカーボタン)
        spec_row = QHBoxLayout()
        spec_row.setSpacing(6)

        self.color_swatch = QLabel()
        self.color_swatch.setFixedSize(36, 24)
        spec_row.addWidget(self.color_swatch)

        hex_lbl = QLabel("HEX:")
        hex_lbl.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 11px; border: none;")
        spec_row.addWidget(hex_lbl)

        self.hex_input = QLineEdit()
        self.hex_input.setFixedSize(70, 24)
        self.hex_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: #191410;
                color: #ffffff;
                border: 1px solid #3d2f21;
                border-radius: 2px;
                padding: 2px 4px;
                font-family: monospace;
                font-size: 11px;
            }}
            QLineEdit:focus {{
                border: 1px solid {Theme.BRASS_LIGHT};
            }}
        """)
        self.hex_input.textChanged.connect(self._on_hex_changed)
        spec_row.addWidget(self.hex_input)

        spec_row.addStretch()

        detail_btn = QPushButton("🎨 詳細ピッカー...")
        detail_btn.setCursor(Qt.PointingHandCursor)
        detail_btn.setFixedHeight(24)
        detail_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #1e1711;
                color: {Theme.BRASS_LIGHT};
                border: 1px solid #4a3a2a;
                border-radius: 2px;
                padding: 0 8px;
                font-size: 10px;
            }}
            QPushButton:hover {{
                background-color: #2d2218;
                border: 1px solid {Theme.BRASS_LIGHT};
                color: #ffffff;
            }}
        """)
        detail_btn.clicked.connect(self._choose_custom_color)
        spec_row.addWidget(detail_btn)

        c_layout.addLayout(spec_row)
        c_main_layout.addWidget(custom_box)

        # 4. リアルタイムプレビュー
        prev_layout = QHBoxLayout()
        prev_lbl = QLabel("表示プレビュー:")
        prev_lbl.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 12px;")
        prev_layout.addWidget(prev_lbl)

        self.preview_pill = PillTag(current_name, color=self.selected_color, is_checkable=False)
        prev_layout.addWidget(self.preview_pill)
        prev_layout.addStretch()
        c_main_layout.addLayout(prev_layout)

        # 5. ボタンバー
        btn_bar = QHBoxLayout()
        btn_bar.addStretch()

        save_btn = QPushButton("💾  保存")
        save_btn.setFixedSize(85, 30)
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #2e2417;
                color: {Theme.BRASS_LIGHT};
                border: 1px solid {Theme.BRASS_LIGHT};
                font-weight: bold;
                border-radius: 2px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: #443522;
                color: #ffffff;
            }}
        """)
        save_btn.clicked.connect(self._on_save)
        btn_bar.addWidget(save_btn)

        cancel_btn = QPushButton("✕  取消")
        cancel_btn.setFixedSize(80, 30)
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
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
        cancel_btn.clicked.connect(self.reject)
        btn_bar.addWidget(cancel_btn)

        c_main_layout.addLayout(btn_bar)

        # 初期値同期
        init_col = QColor(self.selected_color)
        if not init_col.isValid():
            init_col = QColor("#546e7a")
            self.selected_color = "#546e7a"

        self._updating = True
        self.r_slider.setValue(init_col.red())
        self.g_slider.setValue(init_col.green())
        self.b_slider.setValue(init_col.blue())
        self.r_val.setText(str(init_col.red()))
        self.g_val.setText(str(init_col.green()))
        self.b_val.setText(str(init_col.blue()))
        self.hex_input.setText(self.selected_color)
        self._updating = False

        self._update_swatch_and_preview()

    def _on_slider_changed(self):
        if self._updating:
            return
        r = self.r_slider.value()
        g = self.g_slider.value()
        b = self.b_slider.value()
        self.r_val.setText(str(r))
        self.g_val.setText(str(g))
        self.b_val.setText(str(b))

        hex_code = f"#{r:02x}{g:02x}{b:02x}"
        self.selected_color = hex_code

        self._updating = True
        self.hex_input.setText(hex_code)
        self._updating = False

        self._update_swatch_and_preview()

    def _on_hex_changed(self, text):
        if self._updating:
            return
        clean = text.strip()
        if len(clean) == 7 and clean.startswith("#"):
            col = QColor(clean)
            if col.isValid():
                self.selected_color = clean.lower()
                self._updating = True
                self.r_slider.setValue(col.red())
                self.g_slider.setValue(col.green())
                self.b_slider.setValue(col.blue())
                self.r_val.setText(str(col.red()))
                self.g_val.setText(str(col.green()))
                self.b_val.setText(str(col.blue()))
                self._updating = False
                self._update_swatch_and_preview()

    def _select_preset_color(self, hex_color):
        col = QColor(hex_color)
        if not col.isValid():
            return
        self.selected_color = hex_color.lower()
        self._updating = True
        self.r_slider.setValue(col.red())
        self.g_slider.setValue(col.green())
        self.b_slider.setValue(col.blue())
        self.r_val.setText(str(col.red()))
        self.g_val.setText(str(col.green()))
        self.b_val.setText(str(col.blue()))
        self.hex_input.setText(self.selected_color)
        self._updating = False
        self._update_swatch_and_preview()

    def _choose_custom_color(self):
        col = QColorDialog.getColor(QColor(self.selected_color), self, "しおりタグのカラー選択")
        if col.isValid():
            self._select_preset_color(col.name())

    def _update_swatch_and_preview(self):
        self.color_swatch.setStyleSheet(
            f"background-color: {self.selected_color}; border: 1px solid {Theme.BRASS_LIGHT}; border-radius: 2px;"
        )
        self._refresh_palette_styles()
        self._update_preview()

    def _refresh_palette_styles(self):
        sel_lower = self.selected_color.lower()
        for btn, c_hex in self.color_buttons:
            is_sel = (c_hex.lower() == sel_lower)
            border = f"2px solid {Theme.BRASS_LIGHT}" if is_sel else "1px solid #3d2f21"
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {c_hex};
                    border: {border};
                    border-radius: 15px;
                }}
                QPushButton:hover {{
                    border: 2px solid #ffffff;
                }}
            """)

    def _update_preview(self):
        text = self.name_edit.text().strip() or "タグ名"
        self.preview_pill.label.setText(text)
        self.preview_pill.tag_color = self.selected_color
        self.preview_pill.dot.setStyleSheet(f"background-color: {self.selected_color}; border-radius: 4px;")

    def _on_save(self):
        new_name = self.name_edit.text().strip()
        if not new_name:
            QMessageBox.warning(self, "エラー", "タグ名を入力してください。")
            return

        is_glob = 1 if self.global_check.isChecked() else 0
        self.db.update_tag(self.tag_id, new_name=new_name, new_color=self.selected_color, is_global=is_glob)
        self.accept()


class DomainEditDialog(QDialog):
    """西洋古書調のドメイン・表示名編集ダイアログ"""

    def __init__(self, domain="", label="", parent=None):
        super().__init__(parent)
        self.original_domain = domain
        self.result_domain = domain
        self.result_label = label
        self.setWindowTitle("ドメイン表示設定の編集")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.resize(420, 270)
        self.setStyleSheet(Theme.get_application_stylesheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.frame = OrnateFrame(self, bracket_size=14, bg_color="#181310")
        layout.addWidget(self.frame)

        f_layout = QVBoxLayout(self.frame)
        f_layout.setContentsMargins(0, 0, 0, 14)
        f_layout.setSpacing(10)

        self.title_bar = OrnateTitleBar("ドメイン表示設定の編集", parent=self, show_close=True)
        f_layout.addWidget(self.title_bar)

        content_widget = QWidget()
        c_layout = QVBoxLayout(content_widget)
        c_layout.setContentsMargins(16, 4, 16, 0)
        c_layout.setSpacing(10)
        f_layout.addWidget(content_widget)

        # ドメイン入力
        d_lbl = QLabel("ドメイン (例: talto.cc / booth.pm):")
        d_lbl.setStyleSheet(f"color: {Theme.TEXT_WHITE}; font-size: 12px; font-weight: bold;")
        c_layout.addWidget(d_lbl)

        self.domain_edit = QLineEdit(domain)
        self.domain_edit.setFixedHeight(28)
        self.domain_edit.setPlaceholderText("例: talto.cc")
        self.domain_edit.setStyleSheet(f"""
            QLineEdit {{
                background-color: #191410;
                color: #ffffff;
                border: 1px solid {Theme.BRASS_BASE};
                border-radius: 2px;
                padding: 4px 8px;
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border: 1px solid {Theme.BRASS_LIGHT};
            }}
        """)
        c_layout.addWidget(self.domain_edit)

        # 表示名入力
        l_lbl = QLabel("表示名 (例: TALTO / Booth):")
        l_lbl.setStyleSheet(f"color: {Theme.TEXT_WHITE}; font-size: 12px; font-weight: bold;")
        c_layout.addWidget(l_lbl)

        self.label_edit = QLineEdit(label)
        self.label_edit.setFixedHeight(28)
        self.label_edit.setPlaceholderText("例: TALTO")
        self.label_edit.setStyleSheet(f"""
            QLineEdit {{
                background-color: #191410;
                color: #ffffff;
                border: 1px solid {Theme.BRASS_BASE};
                border-radius: 2px;
                padding: 4px 8px;
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border: 1px solid {Theme.BRASS_LIGHT};
            }}
        """)
        c_layout.addWidget(self.label_edit)

        c_layout.addSpacing(6)

        # ボタンバー
        btn_bar = QHBoxLayout()
        btn_bar.addStretch()

        save_btn = QPushButton("💾 保存")
        save_btn.setFixedSize(85, 30)
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #2e2417;
                color: {Theme.BRASS_LIGHT};
                border: 1px solid {Theme.BRASS_LIGHT};
                border-radius: 2px;
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: #443522;
                color: #ffffff;
            }}
        """)
        save_btn.clicked.connect(self._on_save)
        btn_bar.addWidget(save_btn)

        cancel_btn = QPushButton("✕ 取消")
        cancel_btn.setFixedSize(70, 30)
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
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
        cancel_btn.clicked.connect(self.reject)
        btn_bar.addWidget(cancel_btn)

        c_layout.addLayout(btn_bar)

    def _on_save(self):
        d = app_settings.clean_domain(self.domain_edit.text().strip())
        l = self.label_edit.text().strip()
        if not d:
            QMessageBox.warning(self, "エラー", "有効なドメインを入力してください。")
            return
        if not l:
            QMessageBox.warning(self, "エラー", "表示名を入力してください。")
            return
        self.result_domain = d
        self.result_label = l
        self.accept()


class SettingsDialog(QDialog):
    """西洋古書調の設定ダイアログ（タグ管理・ショートカットキー設定・ドメイン設定・Notion連携）"""
    settings_saved = Signal()
    tags_changed = Signal()

    def __init__(self, db=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("魔導書架  ―  環境設定")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.resize(760, 650)
        self.setStyleSheet(Theme.get_application_stylesheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 外枠フレーム
        self.frame = OrnateFrame(self, bracket_size=16, bg_color="#181310")
        layout.addWidget(self.frame)

        f_layout = QVBoxLayout(self.frame)
        f_layout.setContentsMargins(0, 0, 0, 16)
        f_layout.setSpacing(10)

        # 画面デザイン一体型タイトルバー
        self.title_bar = OrnateTitleBar("魔導書架  ―  環境設定", parent=self, show_close=True)
        f_layout.addWidget(self.title_bar)

        content_widget = QWidget()
        c_layout = QVBoxLayout(content_widget)
        c_layout.setContentsMargins(16, 4, 16, 0)
        c_layout.setSpacing(10)
        f_layout.addWidget(content_widget)

        # 2. タブウィジェット
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid #4a3a2a;
                background-color: #14100c;
                border-radius: 2px;
            }}
            QTabBar::tab {{
                background-color: #1c1611;
                color: #bfa990;
                border: 1px solid #3d2f21;
                border-bottom: none;
                padding: 6px 14px;
                font-size: 11px;
                font-family: {Theme.FONT_SERIF};
                margin-right: 2px;
                border-top-left-radius: 2px;
                border-top-right-radius: 2px;
            }}
            QTabBar::tab:selected {{
                background-color: #2b2014;
                color: #f1c40f;
                border: 1px solid {Theme.BRASS_LIGHT};
                border-bottom: 1px solid #14100c;
                font-weight: bold;
            }}
            QTabBar::tab:hover:!selected {{
                background-color: #241c15;
                color: #ffffff;
            }}
        """)

        # タブ1: しおり・タグ管理
        self.tabs.addTab(self._build_tags_tab(), "🏷  しおり・タグ管理")

        # タブ2: ショートカットキー設定
        self.tabs.addTab(self._build_shortcuts_tab(), "⌨  ショートカット")

        # タブ3: ドメイン表示設定
        self.tabs.addTab(self._build_domains_tab(), "🌐  ドメイン設定")

        # タブ4: バックアップ・復元
        self.tabs.addTab(self._build_backup_tab(), "💾  バックアップ・復元")

        # タブ5: Notion連携設定
        self.tabs.addTab(self._build_notion_tab(), "🔗  Notion連携・環境")

        c_layout.addWidget(self.tabs)

        # 3. ボタンバー
        btn_bar = QHBoxLayout()
        btn_bar.addStretch()

        self.save_btn = QPushButton("💾  設定を保存")
        self.save_btn.setFixedSize(115, 32)
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #2e2417;
                color: {Theme.BRASS_LIGHT};
                border: 1px solid {Theme.BRASS_LIGHT};
                font-weight: bold;
                border-radius: 2px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: #443522;
                color: #ffffff;
            }}
        """)
        self.save_btn.clicked.connect(self._save_settings)
        btn_bar.addWidget(self.save_btn)

        self.close_btn = QPushButton("閉じる")
        self.close_btn.setFixedSize(80, 32)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setStyleSheet(f"""
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
        self.close_btn.clicked.connect(self.accept)
        btn_bar.addWidget(self.close_btn)

        c_layout.addLayout(btn_bar)

        self._load_settings()
        self._load_tags_table()

    # =========================================================================
    # タグ一覧管理タブ（グローバルタグ管理・ローカルタグ管理の2画面構成）
    # =========================================================================
    def _build_tags_tab(self):
        """しおり・タグ管理タブの構築（グローバルタグ画面とローカルタグ画面のサブタブ分割）"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # サブタブウィジェット
        self.tag_sub_tabs = QTabWidget()
        self.tag_sub_tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid #3d2f21;
                background-color: #16110d;
                border-radius: 2px;
            }}
            QTabBar::tab {{
                background-color: #1b1510;
                color: #bfa990;
                border: 1px solid #3d2f21;
                border-bottom: none;
                padding: 5px 14px;
                font-size: 11px;
                font-family: {Theme.FONT_SERIF};
                margin-right: 2px;
                border-top-left-radius: 2px;
                border-top-right-radius: 2px;
            }}
            QTabBar::tab:selected {{
                background-color: #261c13;
                color: #f1c40f;
                border: 1px solid {Theme.BRASS_LIGHT};
                border-bottom: 1px solid #16110d;
                font-weight: bold;
            }}
            QTabBar::tab:hover:!selected {{
                background-color: #221a14;
                color: #ffffff;
            }}
        """)

        # 1. グローバルタグ管理画面
        self.global_tab_widget = self._build_single_tag_tab(is_global=True)
        self.tag_sub_tabs.addTab(self.global_tab_widget, "🌐  グローバルタグ設定 (右クリック用)")

        # 2. ローカルタグ管理画面
        self.local_tab_widget = self._build_single_tag_tab(is_global=False)
        self.tag_sub_tabs.addTab(self.local_tab_widget, "🏷  ローカルタグ設定 (詳細画面用)")

        layout.addWidget(self.tag_sub_tabs)

        # 互換プロパティの初期バインド
        self.tag_table = self.global_tag_table
        self.new_tag_input = self.new_global_tag_input
        self.tag_filter_input = self.global_tag_filter_input
        self.edit_btn = self.global_edit_btn
        self.tag_count_label = self.global_tag_count_label

        self.tag_sub_tabs.currentChanged.connect(self._on_tag_sub_tab_changed)

        return widget

    def _build_single_tag_tab(self, is_global=True):
        """個別のタグ管理パネル（グローバル用またはローカル用）を構築"""
        panel = QWidget()
        p_layout = QVBoxLayout(panel)
        p_layout.setContentsMargins(12, 12, 12, 12)
        p_layout.setSpacing(8)

        # ガイド説明文
        if is_global:
            guide_txt = "🌐 <b>グローバルタグ</b>: シナリオカードを右クリックした際にワンクリックで複数設定できる重要タグです。<br><span style='color: #a8947f;'>（初期値: CoC、マダミス、未通過、通過済み、GM可 など）</span>"
        else:
            guide_txt = "🏷 <b>ローカルタグ</b>: 各シナリオの詳細画面（本を開く）から自由に付与・設定できる個別タグです。<br><span style='color: #a8947f;'>（キャンペーン名、探索者名、独自カテゴリなど自由に追加可能）</span>"

        guide_lbl = QLabel(guide_txt)
        guide_lbl.setStyleSheet("color: #dcd0bd; font-size: 11px; line-height: 1.4;")
        guide_lbl.setWordWrap(True)
        p_layout.addWidget(guide_lbl)

        p_layout.addWidget(OrnateDivider(self, height=6))

        # 新規タグ追加入力バー
        add_bar = QHBoxLayout()
        add_bar.setSpacing(8)

        new_in = QLineEdit()
        placeholder = "新しいグローバルタグ名を入力..." if is_global else "新しいローカルタグ名を入力..."
        new_in.setPlaceholderText(placeholder)
        new_in.setFixedHeight(30)
        new_in.setStyleSheet(f"""
            QLineEdit {{
                background-color: #191410;
                color: #ffffff;
                border: 1px solid {Theme.BRASS_BASE};
                border-radius: 2px;
                padding: 4px 8px;
                font-size: 12px;
            }}
            QLineEdit:focus {{
                border: 1px solid {Theme.BRASS_LIGHT};
            }}
        """)
        new_in.returnPressed.connect(lambda: self._on_add_tag(is_global=is_global))
        add_bar.addWidget(new_in)

        add_btn = QPushButton("＋  タグ作成")
        add_btn.setFixedSize(95, 30)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #261d15;
                color: {Theme.BRASS_LIGHT};
                border: 1px solid {Theme.BRASS_BASE};
                border-radius: 2px;
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: #3b2c1d;
                border: 1px solid {Theme.BRASS_LIGHT};
                color: #ffffff;
            }}
        """)
        add_btn.clicked.connect(lambda: self._on_add_tag(is_global=is_global))
        add_bar.addWidget(add_btn)
        p_layout.addLayout(add_bar)

        # 絞り込み検索バー
        filter_bar = QHBoxLayout()
        filter_lbl = QLabel("🔍 絞り込み:")
        filter_lbl.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 11px;")
        filter_bar.addWidget(filter_lbl)

        filter_in = QLineEdit()
        filter_in.setPlaceholderText("タグ名で検索...")
        filter_in.setFixedHeight(26)
        filter_in.setStyleSheet(f"""
            QLineEdit {{
                background-color: #15100c;
                color: #dcd0bd;
                border: 1px solid #3d2f21;
                border-radius: 2px;
                padding: 2px 6px;
                font-size: 11px;
            }}
        """)
        filter_in.textChanged.connect(self._load_tags_table)
        filter_bar.addWidget(filter_in)
        p_layout.addLayout(filter_bar)

        # タグ一覧テーブル
        table = QTableWidget()
        table.setColumnCount(3)
        header_tag_name = "グローバルタグ名 (しおり)" if is_global else "ローカルタグ名"
        table.setHorizontalHeaderLabels(["色", header_tag_name, "使用シナリオ数"])
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(28)
        table.horizontalHeader().setStretchLastSection(False)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        table.setColumnWidth(0, 46)
        table.setColumnWidth(2, 130)
        table.itemDoubleClicked.connect(lambda _: self._on_edit_tag(target_table=table))

        table.setStyleSheet(f"""
            QTableWidget {{
                background-color: #140f0c;
                alternate-background-color: #1a1410;
                color: #f2e6d6;
                gridline-color: #2e2318;
                border: 1px solid #4a3a2a;
                border-radius: 2px;
                selection-background-color: #38291b;
                selection-color: #ffffff;
                font-family: {Theme.FONT_SERIF};
                font-size: 12px;
            }}
            QTableWidget::item {{
                padding: 2px 8px;
                border-bottom: 1px solid #241b14;
            }}
            QTableWidget::item:selected {{
                background-color: #38291b;
                color: #f1c40f;
                font-weight: bold;
            }}
            QHeaderView::section {{
                background-color: #221a14;
                color: {Theme.BRASS_LIGHT};
                padding: 6px 8px;
                border: 1px solid #3d2f21;
                font-weight: bold;
                font-size: 12px;
                font-family: {Theme.FONT_SERIF};
            }}
        """)
        p_layout.addWidget(table)

        # アクションバー
        action_bar = QHBoxLayout()
        action_bar.setSpacing(8)

        edit_btn = QPushButton("✎  タグの編集...")
        edit_btn.setFixedSize(115, 28)
        edit_btn.setCursor(Qt.PointingHandCursor)
        edit_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #1e1711;
                color: {Theme.BRASS_LIGHT};
                border: 1px solid #4a3a2a;
                border-radius: 2px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: #2d2218;
                border: 1px solid {Theme.BRASS_LIGHT};
                color: #ffffff;
            }}
        """)
        edit_btn.clicked.connect(lambda: self._on_edit_tag(target_table=table))
        action_bar.addWidget(edit_btn)

        del_btn = QPushButton("🗑  タグを削除")
        del_btn.setFixedSize(105, 28)
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #1e1711;
                color: #c97a7e;
                border: 1px solid #4a3a2a;
                border-radius: 2px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: #3d1b1e;
                border: 1px solid #d32f2f;
                color: #ff9999;
            }}
        """)
        del_btn.clicked.connect(lambda: self._on_delete_tag(target_table=table))
        action_bar.addWidget(del_btn)

        action_bar.addStretch()

        cnt_lbl = QLabel("登録タグ: 0 種類")
        cnt_lbl.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 11px;")
        action_bar.addWidget(cnt_lbl)
        p_layout.addLayout(action_bar)

        if is_global:
            self.new_global_tag_input = new_in
            self.global_tag_filter_input = filter_in
            self.global_tag_table = table
            self.global_edit_btn = edit_btn
            self.global_del_btn = del_btn
            self.global_tag_count_label = cnt_lbl
        else:
            self.new_local_tag_input = new_in
            self.local_tag_filter_input = filter_in
            self.local_tag_table = table
            self.local_edit_btn = edit_btn
            self.local_del_btn = del_btn
            self.local_tag_count_label = cnt_lbl

        return panel

    def _on_tag_sub_tab_changed(self, idx):
        """サブタブ切り替え時に互換プロパティを更新"""
        if idx == 0:
            self.tag_table = self.global_tag_table
            self.new_tag_input = self.new_global_tag_input
            self.tag_filter_input = self.global_tag_filter_input
            self.edit_btn = self.global_edit_btn
            self.tag_count_label = self.global_tag_count_label
        else:
            self.tag_table = self.local_tag_table
            self.new_tag_input = self.new_local_tag_input
            self.tag_filter_input = self.local_tag_filter_input
            self.edit_btn = self.local_edit_btn
            self.tag_count_label = self.local_tag_count_label

    def _load_tags_table(self, select_tag_id=None):
        """グローバルタグおよびローカルタグの両テーブルにデータを反映"""
        if not self.db:
            return

        # 1. グローバルタグの読み込み
        try:
            global_tags = self.db.get_tags_with_counts(is_global=True)
        except Exception:
            global_tags = [(t[0], t[1], 0, t[2] if len(t) > 2 else None, 1) for t in self.db.get_global_tags()]

        g_filter = self.global_tag_filter_input.text().strip().lower()
        g_filtered = [t for t in global_tags if not g_filter or g_filter in t[1].lower()]
        g_target_row = self._populate_tag_table(self.global_tag_table, g_filtered, select_tag_id)
        self.global_tag_count_label.setText(f"登録グローバルタグ: {len(global_tags)} 種類")

        # 2. ローカルタグの読み込み
        try:
            local_tags = self.db.get_tags_with_counts(is_global=False)
        except Exception:
            local_tags = [(t[0], t[1], 0, t[2] if len(t) > 2 else None, 0) for t in self.db.get_local_tags()]

        l_filter = self.local_tag_filter_input.text().strip().lower()
        l_filtered = [t for t in local_tags if not l_filter or l_filter in t[1].lower()]
        l_target_row = self._populate_tag_table(self.local_tag_table, l_filtered, select_tag_id)
        self.local_tag_count_label.setText(f"登録ローカルタグ: {len(local_tags)} 種類")

        # 選択対象があれば、該当タブをアクティブにしてスクロール
        if select_tag_id is not None:
            if g_target_row is not None:
                self.tag_sub_tabs.setCurrentIndex(0)
                self.global_tag_table.selectRow(g_target_row)
                self.global_tag_table.scrollToItem(self.global_tag_table.item(g_target_row, 1))
            elif l_target_row is not None:
                self.tag_sub_tabs.setCurrentIndex(1)
                self.local_tag_table.selectRow(l_target_row)
                self.local_tag_table.scrollToItem(self.local_tag_table.item(l_target_row, 1))

    def _populate_tag_table(self, table, tag_list, select_tag_id):
        """テーブルウィジェットに行データを流し込むヘルパー"""
        table.setRowCount(len(tag_list))
        target_row = None
        for row, item_tuple in enumerate(tag_list):
            tid = item_tuple[0]
            name = item_tuple[1]
            count = item_tuple[2]
            color = item_tuple[3] if len(item_tuple) > 3 else None
            is_glob = item_tuple[4] if len(item_tuple) > 4 else 0

            # 列0: カラーサークル
            item_col = QTableWidgetItem()
            pix = make_color_circle_pixmap(color, size=14)
            item_col.setIcon(pix)
            item_col.setTextAlignment(Qt.AlignCenter)
            item_col.setData(Qt.UserRole, tid)
            item_col.setData(Qt.UserRole + 1, name)
            item_col.setData(Qt.UserRole + 2, color)
            item_col.setData(Qt.UserRole + 3, is_glob)

            # 列1: タグ名
            prefix = "🌐  " if is_glob else "🏷  "
            item_name = QTableWidgetItem(f"{prefix}{name}")
            item_name.setData(Qt.UserRole, tid)
            item_name.setData(Qt.UserRole + 1, name)
            item_name.setData(Qt.UserRole + 2, color)
            item_name.setData(Qt.UserRole + 3, is_glob)

            # 列2: 使用件数
            if count > 0:
                count_str = f"{count} 冊で使用中"
                item_count = QTableWidgetItem(count_str)
                item_count.setForeground(QColor("#f1c40f"))
            else:
                count_str = "未使用 (0 冊)"
                item_count = QTableWidgetItem(count_str)
                item_count.setForeground(QColor("#776655"))

            item_count.setTextAlignment(Qt.AlignCenter)

            table.setItem(row, 0, item_col)
            table.setItem(row, 1, item_name)
            table.setItem(row, 2, item_count)

            if select_tag_id is not None and tid == select_tag_id:
                target_row = row

        return target_row

    def _on_add_tag(self, is_global=None):
        """新規タグの追加（グローバル/ローカルを判定）"""
        if not self.db:
            return

        if is_global is None:
            is_global = (self.tag_sub_tabs.currentIndex() == 0)

        in_widget = self.new_global_tag_input if is_global else self.new_local_tag_input
        name = in_widget.text().strip()

        # 互換用フォールバック
        if not name and hasattr(self, "new_tag_input") and self.new_tag_input.text().strip():
            name = self.new_tag_input.text().strip()

        if not name:
            return

        existing = self.db.get_tag_by_name(name)
        if existing:
            tag_kind = "グローバルタグ" if existing[3] else "ローカルタグ"
            QMessageBox.information(self, "案内", f"タグ「{name}」は既に{tag_kind}として登録されています。")
            return

        tid = self.db.add_tag(name, is_global=1 if is_global else 0)
        if tid:
            in_widget.clear()
            if hasattr(self, "new_tag_input"):
                self.new_tag_input.clear()
            self._load_tags_table(select_tag_id=tid)
            self.tags_changed.emit()

    def _on_edit_tag(self, target_table=None):
        """選択中タグの編集（名前、色、グローバル/ローカル区分変更）"""
        if not self.db:
            return

        table = target_table or self.tag_table
        row = table.currentRow()
        if row < 0:
            QMessageBox.information(self, "案内", "編集するタグを一覧から選択してください。")
            return

        item = table.item(row, 1)
        tid = item.data(Qt.UserRole)
        name = item.data(Qt.UserRole + 1)
        color = item.data(Qt.UserRole + 2)
        is_glob = item.data(Qt.UserRole + 3)

        dlg = TagEditDialog(tid, name, color, self.db, is_global=is_glob, parent=self)
        if dlg.exec() == QDialog.Accepted:
            self._load_tags_table(select_tag_id=tid)
            self.tags_changed.emit()

    def _on_delete_tag(self, target_table=None):
        """選択中タグの削除（付与状況の警告確認付き）"""
        if not self.db:
            return

        table = target_table or self.tag_table
        row = table.currentRow()
        if row < 0:
            QMessageBox.information(self, "案内", "削除するタグを一覧から選択してください。")
            return

        item = table.item(row, 1)
        tid = item.data(Qt.UserRole)
        name = item.data(Qt.UserRole + 1)

        counts_dict = dict((t[0], t[2]) for t in self.db.get_tags_with_counts())
        c = counts_dict.get(tid, 0)

        if c > 0:
            msg = (
                f"タグ「{name}」は現在 {c} 冊のシナリオに付与されています。\n"
                f"削除すると、すべてのシナリオからこのタグが除籍されます。\n\n"
                f"本当に削除しますか？"
            )
        else:
            msg = f"タグ「{name}」を書架目録から削除しますか？"

        reply = QMessageBox.question(
            self,
            "タグの削除確認",
            msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.db.delete_tag(tid)
            self._load_tags_table()
            self.tags_changed.emit()

    # =========================================================================
    # ショートカットタブ
    # =========================================================================
    def _build_shortcuts_tab(self):
        """ショートカットキー設定タブ"""
        widget = QWidget()
        v_layout = QVBoxLayout(widget)
        v_layout.setContentsMargins(14, 14, 14, 14)
        v_layout.setSpacing(10)

        info_lbl = QLabel("※ 各項目の枠内をクリックし、キーボードの任意のキーを押して設定してください。")
        info_lbl.setStyleSheet("color: #a8947f; font-size: 11px;")
        v_layout.addWidget(info_lbl)

        grid = QGridLayout()
        grid.setSpacing(8)
        grid.setContentsMargins(4, 4, 4, 4)

        self.shortcut_inputs = {}
        for row, (k, label_text) in enumerate(app_settings.SHORTCUT_LABELS.items()):
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"color: {Theme.TEXT_WHITE}; font-size: 12px; font-family: {Theme.FONT_SERIF};")
            grid.addWidget(lbl, row, 0)

            seq_edit = QKeySequenceEdit()
            seq_edit.setFixedHeight(28)
            seq_edit.setStyleSheet(f"""
                QKeySequenceEdit {{
                    background-color: #1b1510;
                    color: #f1c40f;
                    border: 1px solid #5a4530;
                    border-radius: 2px;
                    padding: 2px 6px;
                    font-size: 12px;
                    font-weight: bold;
                }}
                QKeySequenceEdit:focus {{
                    border: 1px solid {Theme.BRASS_LIGHT};
                    background-color: #241c14;
                }}
            """)
            grid.addWidget(seq_edit, row, 1)
            self.shortcut_inputs[k] = seq_edit

        v_layout.addLayout(grid)
        v_layout.addStretch()

        # デフォルトに戻すボタン
        reset_bar = QHBoxLayout()
        reset_bar.addStretch()
        reset_btn = QPushButton("↺  初期設定に戻す")
        reset_btn.setCursor(Qt.PointingHandCursor)
        reset_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #18130f;
                color: #a8947f;
                border: 1px solid #3d2f21;
                border-radius: 2px;
                padding: 4px 10px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                color: {Theme.BRASS_LIGHT};
                border: 1px solid {Theme.BRASS_BASE};
            }}
        """)
        reset_btn.clicked.connect(self._reset_shortcuts_to_default)
        reset_bar.addWidget(reset_btn)
        v_layout.addLayout(reset_bar)

        return widget

    # =========================================================================
    # Notion連携・環境タブ
    # =========================================================================
    def _build_notion_tab(self):
        """Notion連携・環境タブ"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        notion_lbl = QLabel("🔗  Notion 書架同調（同期）設定")
        notion_lbl.setStyleSheet(f"color: {Theme.BRASS_LIGHT}; font-weight: bold; font-size: 13px;")
        layout.addWidget(notion_lbl)

        grid = QGridLayout()
        grid.setSpacing(8)

        # 1. API キー (Token)
        grid.addWidget(QLabel("API キー (Token):"), 0, 0)
        token_row = QHBoxLayout()
        self.token_edit = QLineEdit()
        self.token_edit.setEchoMode(QLineEdit.Password)
        self.token_edit.setPlaceholderText("内部インテグレーションシークレット (ntn_... または secret_...)")
        self.token_edit.setStyleSheet(f"""
            QLineEdit {{
                background-color: #191410;
                color: #ffffff;
                border: 1px solid {Theme.BRASS_BASE};
                border-radius: 2px;
                padding: 4px 6px;
            }}
            QLineEdit:focus {{
                border: 1px solid {Theme.BRASS_LIGHT};
            }}
        """)
        token_row.addWidget(self.token_edit)

        token_btn = QPushButton("🔗 トークン生成ページを開く")
        token_btn.setCursor(Qt.PointingHandCursor)
        token_btn.setFixedHeight(26)
        token_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #1e1711;
                color: {Theme.BRASS_LIGHT};
                border: 1px solid #4a3a2a;
                border-radius: 2px;
                padding: 0 8px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: #2d2218;
                border: 1px solid {Theme.BRASS_LIGHT};
                color: #ffffff;
            }}
        """)
        token_btn.clicked.connect(self._open_token_page)
        token_row.addWidget(token_btn)
        grid.addLayout(token_row, 0, 1)

        # 2. リンクURLからID生成
        grid.addWidget(QLabel("リンクURLからID生成:"), 1, 0)
        url_row = QHBoxLayout()
        self.page_url_input = QLineEdit()
        self.page_url_input.setPlaceholderText("NotionデータベースページのURL（共有リンク）を貼り付け...")
        self.page_url_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: #191410;
                color: #ffffff;
                border: 1px solid {Theme.BRASS_BASE};
                border-radius: 2px;
                padding: 4px 6px;
            }}
            QLineEdit:focus {{
                border: 1px solid {Theme.BRASS_LIGHT};
            }}
        """)
        self.page_url_input.textChanged.connect(self._on_url_input_changed)
        url_row.addWidget(self.page_url_input)

        gen_id_btn = QPushButton("⚡ IDを生成")
        gen_id_btn.setCursor(Qt.PointingHandCursor)
        gen_id_btn.setFixedHeight(26)
        gen_id_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #261d15;
                color: {Theme.BRASS_LIGHT};
                border: 1px solid {Theme.BRASS_BASE};
                border-radius: 2px;
                padding: 0 10px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #3b2c1d;
                border: 1px solid {Theme.BRASS_LIGHT};
                color: #ffffff;
            }}
        """)
        gen_id_btn.clicked.connect(self._generate_id_from_url)
        url_row.addWidget(gen_id_btn)
        grid.addLayout(url_row, 1, 1)

        # 3. データベース ID
        grid.addWidget(QLabel("データベース ID:"), 2, 0)
        id_row = QHBoxLayout()
        self.db_id_edit = QLineEdit()
        self.db_id_edit.setPlaceholderText("32桁の英数字（上記のURL貼り付けで自動生成されます）")
        self.db_id_edit.setStyleSheet(f"""
            QLineEdit {{
                background-color: #191410;
                color: #ffffff;
                border: 1px solid {Theme.BRASS_BASE};
                border-radius: 2px;
                padding: 4px 6px;
                font-family: monospace;
            }}
            QLineEdit:focus {{
                border: 1px solid {Theme.BRASS_LIGHT};
            }}
        """)
        self.db_id_edit.textChanged.connect(self._on_db_id_direct_input)
        id_row.addWidget(self.db_id_edit)

        self.id_status_lbl = QLabel("")
        self.id_status_lbl.setStyleSheet("color: #69db7c; font-size: 11px;")
        id_row.addWidget(self.id_status_lbl)
        grid.addLayout(id_row, 2, 1)

        # 4. API 利用間隔（秒）
        grid.addWidget(QLabel("API 利用間隔 (秒):"), 3, 0)
        interval_row = QHBoxLayout()
        self.api_interval_spin = QDoubleSpinBox()
        self.api_interval_spin.setRange(0.1, 30.0)
        self.api_interval_spin.setSingleStep(0.1)
        self.api_interval_spin.setDecimals(1)
        self.api_interval_spin.setSuffix(" 秒")
        self.api_interval_spin.setValue(app_settings.get_api_interval())
        self.api_interval_spin.setFixedWidth(110)
        self.api_interval_spin.setStyleSheet(f"""
            QDoubleSpinBox {{
                background-color: #191410;
                color: #ffffff;
                border: 1px solid {Theme.BRASS_BASE};
                border-radius: 2px;
                padding: 4px 6px;
                font-family: monospace;
            }}
            QDoubleSpinBox:focus {{
                border: 1px solid {Theme.BRASS_LIGHT};
            }}
        """)
        interval_row.addWidget(self.api_interval_spin)

        reset_interval_btn = QPushButton("↺ 初期値 (0.5秒)")
        reset_interval_btn.setCursor(Qt.PointingHandCursor)
        reset_interval_btn.setFixedHeight(26)
        reset_interval_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #261d14;
                color: {Theme.TEXT_GOLD};
                border: 1px solid {Theme.BRASS_BASE};
                border-radius: 2px;
                padding: 0 10px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: #3b2c1d;
                border: 1px solid {Theme.BRASS_LIGHT};
                color: #ffffff;
            }}
        """)
        reset_interval_btn.clicked.connect(
            lambda: self.api_interval_spin.setValue(app_settings.DEFAULT_API_INTERVAL)
        )
        interval_row.addWidget(reset_interval_btn)

        interval_note = QLabel("※ Notion API（無料枠）のレート制限（平均3回/秒・180回/分）を考慮し、初期値は安全マージンをとった 0.5 秒に設定されています")
        interval_note.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 11px;")
        interval_row.addWidget(interval_note)
        interval_row.addStretch()
        grid.addLayout(interval_row, 3, 1)

        # 5. Notion 取り込み件数上限
        grid.addWidget(QLabel("取り込み件数上限:"), 4, 0)
        limit_row = QHBoxLayout()
        self.notion_limit_spin = QSpinBox()
        self.notion_limit_spin.setRange(0, 9999)
        self.notion_limit_spin.setSingleStep(5)
        self.notion_limit_spin.setSpecialValueText("0 (無制限)")
        self.notion_limit_spin.setSuffix(" 件")
        self.notion_limit_spin.setValue(app_settings.get_notion_import_limit())
        self.notion_limit_spin.setFixedWidth(130)
        self.notion_limit_spin.setStyleSheet(f"""
            QSpinBox {{
                background-color: #191410;
                color: #ffffff;
                border: 1px solid {Theme.BRASS_BASE};
                border-radius: 2px;
                padding: 4px 6px;
                font-family: monospace;
            }}
            QSpinBox:focus {{
                border: 1px solid {Theme.BRASS_LIGHT};
            }}
        """)
        limit_row.addWidget(self.notion_limit_spin)

        reset_limit_btn = QPushButton("↺ 初期値 (10件)")
        reset_limit_btn.setCursor(Qt.PointingHandCursor)
        reset_limit_btn.setFixedHeight(26)
        reset_limit_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #261d14;
                color: {Theme.TEXT_GOLD};
                border: 1px solid {Theme.BRASS_BASE};
                border-radius: 2px;
                padding: 0 10px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: #3b2c1d;
                border: 1px solid {Theme.BRASS_LIGHT};
                color: #ffffff;
            }}
        """)
        reset_limit_btn.clicked.connect(
            lambda: self.notion_limit_spin.setValue(app_settings.DEFAULT_NOTION_IMPORT_LIMIT)
        )
        limit_row.addWidget(reset_limit_btn)

        limit_note = QLabel("※ 1回の同調で取り込む冊数の上限です（残りは次回の同調で続きから取り込みます）。0で無制限")
        limit_note.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 11px;")
        limit_row.addWidget(limit_note)
        limit_row.addStretch()
        grid.addLayout(limit_row, 4, 1)

        # 6. 自動同調（初期値は無効）
        grid.addWidget(QLabel("自動同調:"), 5, 0)
        auto_row = QHBoxLayout()
        auto_enabled, auto_interval = app_settings.get_notion_auto_sync()
        self.auto_sync_check = QCheckBox("バックグラウンドで自動的に同調する")
        self.auto_sync_check.setChecked(auto_enabled)
        self.auto_sync_check.setCursor(Qt.PointingHandCursor)
        self.auto_sync_check.setStyleSheet(f"""
            QCheckBox {{
                color: {Theme.TEXT_WHITE};
                font-size: 12px;
                spacing: 8px;
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
            QCheckBox::indicator:hover {{
                border: 1px solid {Theme.BRASS_LIGHT};
                background-color: #241c14;
            }}
            QCheckBox::indicator:checked {{
                background-color: {Theme.BRASS_BASE};
                border: 1px solid {Theme.BRASS_LIGHT};
            }}
        """)
        auto_row.addWidget(self.auto_sync_check)

        self.auto_sync_interval_spin = QSpinBox()
        self.auto_sync_interval_spin.setRange(0, 1440)
        self.auto_sync_interval_spin.setSingleStep(5)
        self.auto_sync_interval_spin.setSpecialValueText("起動時のみ")
        self.auto_sync_interval_spin.setPrefix("")
        self.auto_sync_interval_spin.setSuffix(" 分ごと")
        self.auto_sync_interval_spin.setValue(auto_interval)
        self.auto_sync_interval_spin.setFixedWidth(130)
        self.auto_sync_interval_spin.setStyleSheet(self.notion_limit_spin.styleSheet())
        self.auto_sync_interval_spin.setEnabled(auto_enabled)
        self.auto_sync_check.toggled.connect(self.auto_sync_interval_spin.setEnabled)
        auto_row.addWidget(self.auto_sync_interval_spin)

        auto_note = QLabel("※ 起動時と一定間隔で同調します。手元と Notion で内容が食い違う本は保留し、手動の同調で確認します")
        auto_note.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 11px;")
        auto_row.addWidget(auto_note)
        auto_row.addStretch()
        grid.addLayout(auto_row, 5, 1)

        layout.addLayout(grid)

        # Notion トークン・ライブラリIDの取得方法ガイド（Rust情報の上に配置）
        guide_box = QFrame()
        guide_box.setStyleSheet(f"""
            QFrame {{
                background-color: #15100c;
                border: 1px solid #3d2f21;
                border-radius: 4px;
                padding: 8px 10px;
            }}
        """)
        g_layout = QVBoxLayout(guide_box)
        g_layout.setContentsMargins(10, 8, 10, 8)
        g_layout.setSpacing(6)

        g_title = QLabel("📖  Notion トークン ＆ データベース ID の取得・生成手順")
        g_title.setStyleSheet(f"color: {Theme.BRASS_LIGHT}; font-weight: bold; font-family: {Theme.FONT_SERIF}; font-size: 12px; border: none;")
        g_layout.addWidget(g_title)

        guide_html = """
        <div style="line-height: 1.45; color: #dcd0bd; font-size: 11px;">
            <div style="margin-bottom: 5px;">
                <b style="color: #e6c887;">① API キー (Token) の発行手順:</b><br>
                1. 右上の「<b>🔗 トークン生成ページを開く</b>」ボタン（または <a style="color: #64b5f6; text-decoration: underline;" href="https://www.notion.so/profile/integrations">Notion トークン生成ページ</a>）を開きます。<br>
                2.「<b>＋ 新しいインテグレーション</b>」を作成し、任意の名前（例:「魔導書架」）を設定して保存します。<br>
                3. 発行された「<b>内部インテグレーションシークレット (トークン)</b>」（<code>ntn_...</code> または <code>secret_...</code>）をコピーして上の「API キー」欄に貼り付けます。
            </div>
            <div>
                <b style="color: #e6c887;">② データベース ID (ライブラリID) の生成手順:</b><br>
                1. Notion でシナリオを管理したいデータベースのページを開きます。<br>
                2. ページ右上の「<b>…</b>」メニュー →「<b>コネクト</b>」から、上記で作成したインテグレーションを接続します（※必須）。<br>
                3. ページの URL（または「リンクをコピー」した URL）を上の<b>「リンクURLからID生成」欄に貼り付けるだけ</b>で、32桁のデータベース ID が自動生成されます。
            </div>
        </div>
        """
        guide_text = QLabel(guide_html)
        guide_text.setWordWrap(True)
        guide_text.setOpenExternalLinks(True)
        guide_text.setStyleSheet("border: none; background: transparent;")
        g_layout.addWidget(guide_text)

        layout.addWidget(guide_box)

        layout.addSpacing(4)
        layout.addWidget(OrnateDivider(self, height=8))

        # Rust DLL 状態
        rust_lbl = QLabel("⚙  Rust コアエンジン")
        rust_lbl.setStyleSheet(f"color: {Theme.BRASS_LIGHT}; font-weight: bold; font-size: 13px;")
        layout.addWidget(rust_lbl)

        dll_exists = os.path.exists("cover_extractor.dll")
        status_text = "cover_extractor.dll : 正常に配置されています" if dll_exists else "cover_extractor.dll : 見つかりません"
        status_color = Theme.BRASS_LIGHT if dll_exists else "#d32f2f"

        self.dll_status_lbl = QLabel(status_text)
        self.dll_status_lbl.setStyleSheet(f"color: {status_color}; font-size: 11px;")
        layout.addWidget(self.dll_status_lbl)

        layout.addStretch()
        return widget

    def _open_token_page(self):
        """Notion トークン生成ページをブラウザで開く"""
        QDesktopServices.openUrl(QUrl("https://www.notion.so/profile/integrations"))

    def _on_url_input_changed(self, text):
        """リンクURL入力時に自動でデータベースIDを生成"""
        cleaned = text.strip()
        if not cleaned:
            return
        extracted_id = extract_notion_id_from_url(cleaned)
        if len(extracted_id) == 32 and re.fullmatch(r"[0-9a-fA-F]{32}", extracted_id):
            self.db_id_edit.blockSignals(True)
            self.db_id_edit.setText(extracted_id)
            self.db_id_edit.blockSignals(False)
            self.id_status_lbl.setText("✓ URLからID生成完了")
            self.id_status_lbl.setStyleSheet("color: #69db7c; font-size: 11px;")

    def _generate_id_from_url(self):
        """ボタンクリック時にURLからデータベースIDを生成"""
        text = self.page_url_input.text().strip() or self.db_id_edit.text().strip()
        if not text:
            QMessageBox.information(self, "案内", "NotionページのURLを貼り付けてください。")
            return
        extracted_id = extract_notion_id_from_url(text)
        if len(extracted_id) == 32 and re.fullmatch(r"[0-9a-fA-F]{32}", extracted_id):
            self.db_id_edit.blockSignals(True)
            self.db_id_edit.setText(extracted_id)
            self.db_id_edit.blockSignals(False)
            self.id_status_lbl.setText("✓ URLからID生成完了")
            self.id_status_lbl.setStyleSheet("color: #69db7c; font-size: 11px;")
        else:
            QMessageBox.warning(
                self,
                "エラー",
                "入力されたURLから有効な32桁のデータベースIDが見つかりませんでした。\nURLを確認してください。",
            )

    def _on_db_id_direct_input(self, text):
        """データベースID欄に直接URLが貼られた場合にも自動抽出"""
        cleaned = text.strip()
        if "notion.so" in cleaned or "/" in cleaned or "?" in cleaned:
            extracted = extract_notion_id_from_url(cleaned)
            if len(extracted) == 32 and re.fullmatch(r"[0-9a-fA-F]{32}", extracted):
                self.db_id_edit.blockSignals(True)
                self.db_id_edit.setText(extracted)
                self.db_id_edit.blockSignals(False)
                self.id_status_lbl.setText("✓ URLからID生成完了")
                self.id_status_lbl.setStyleSheet("color: #69db7c; font-size: 11px;")

    # =========================================================================
    # ドメイン表示設定タブ
    # =========================================================================
    def _build_domains_tab(self):
        """情報元ドメイン設定タブを構築"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # 説明ガイド
        guide_txt = (
            "🌐 <b>情報元ドメインの省略表示設定</b>: 詳細画面の「情報元」に表示されるWeb URLについて、"
            "登録したドメインと一致した場合に指定の省略名（例: Booth、TALTO 等）でリンク表示します。<br>"
            "<span style='color: #a8947f;'>※ サブドメイン（例: shop.booth.pm）も自動的に同一ドメインとして省略表示されます。</span>"
        )
        guide_lbl = QLabel(guide_txt)
        guide_lbl.setStyleSheet("color: #dcd0bd; font-size: 11px; line-height: 1.4;")
        guide_lbl.setWordWrap(True)
        layout.addWidget(guide_lbl)

        layout.addWidget(OrnateDivider(self, height=6))

        # 新規ドメイン追加バー
        add_bar = QHBoxLayout()
        add_bar.setSpacing(8)

        self.new_domain_input = QLineEdit()
        self.new_domain_input.setPlaceholderText("ドメインを入力 (例: talto.cc)...")
        self.new_domain_input.setFixedHeight(30)
        self.new_domain_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: #191410;
                color: #ffffff;
                border: 1px solid {Theme.BRASS_BASE};
                border-radius: 2px;
                padding: 4px 8px;
                font-size: 12px;
            }}
            QLineEdit:focus {{
                border: 1px solid {Theme.BRASS_LIGHT};
            }}
        """)
        self.new_domain_input.returnPressed.connect(self._on_add_domain)
        add_bar.addWidget(self.new_domain_input, 2)

        self.new_domain_label_input = QLineEdit()
        self.new_domain_label_input.setPlaceholderText("表示名 (例: TALTO)...")
        self.new_domain_label_input.setFixedHeight(30)
        self.new_domain_label_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: #191410;
                color: #ffffff;
                border: 1px solid {Theme.BRASS_BASE};
                border-radius: 2px;
                padding: 4px 8px;
                font-size: 12px;
            }}
            QLineEdit:focus {{
                border: 1px solid {Theme.BRASS_LIGHT};
            }}
        """)
        self.new_domain_label_input.returnPressed.connect(self._on_add_domain)
        add_bar.addWidget(self.new_domain_label_input, 2)

        add_btn = QPushButton("＋  ドメイン追加")
        add_btn.setFixedSize(115, 30)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #261d15;
                color: {Theme.BRASS_LIGHT};
                border: 1px solid {Theme.BRASS_BASE};
                border-radius: 2px;
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: #3b2c1d;
                border: 1px solid {Theme.BRASS_LIGHT};
                color: #ffffff;
            }}
        """)
        add_btn.clicked.connect(self._on_add_domain)
        add_bar.addWidget(add_btn)
        layout.addLayout(add_bar)

        # 絞り込み検索バー
        filter_bar = QHBoxLayout()
        filter_lbl = QLabel("🔍 絞り込み:")
        filter_lbl.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 11px;")
        filter_bar.addWidget(filter_lbl)

        self.domain_filter_input = QLineEdit()
        self.domain_filter_input.setPlaceholderText("ドメインまたは表示名で検索...")
        self.domain_filter_input.setFixedHeight(26)
        self.domain_filter_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: #15100c;
                color: #dcd0bd;
                border: 1px solid #3d2f21;
                border-radius: 2px;
                padding: 2px 6px;
                font-size: 11px;
            }}
        """)
        self.domain_filter_input.textChanged.connect(self._filter_domains_table)
        filter_bar.addWidget(self.domain_filter_input)
        layout.addLayout(filter_bar)

        # ドメイン一覧テーブル
        self.domain_table = QTableWidget()
        self.domain_table.setColumnCount(2)
        self.domain_table.setHorizontalHeaderLabels(["ドメイン (ホスト名)", "表示名 (省略名)"])
        self.domain_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.domain_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.domain_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.domain_table.setAlternatingRowColors(True)
        self.domain_table.verticalHeader().setVisible(False)
        self.domain_table.verticalHeader().setDefaultSectionSize(28)
        self.domain_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.domain_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.domain_table.cellDoubleClicked.connect(self._edit_selected_domain)
        self.domain_table.setStyleSheet(f"""
            QTableWidget {{
                background-color: #16120e;
                alternate-background-color: #1a1510;
                color: {Theme.TEXT_WHITE};
                gridline-color: #2b2014;
                border: 1px solid #3d2f21;
                font-size: 12px;
                font-family: {Theme.FONT_SERIF};
            }}
            QTableWidget::item:selected {{
                background-color: #3b2c1d;
                color: {Theme.BRASS_LIGHT};
            }}
            QHeaderView::section {{
                background-color: #201812;
                color: {Theme.BRASS_LIGHT};
                border: 1px solid #3d2f21;
                padding: 4px;
                font-weight: bold;
                font-size: 11px;
            }}
        """)
        layout.addWidget(self.domain_table)

        # テーブル操作バー
        bar = QHBoxLayout()
        self.domain_count_label = QLabel("登録件数: 0 件")
        self.domain_count_label.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 11px;")
        bar.addWidget(self.domain_count_label)

        bar.addStretch()

        self.domain_edit_btn = QPushButton("✎  編集")
        self.domain_edit_btn.setFixedSize(75, 26)
        self.domain_edit_btn.setCursor(Qt.PointingHandCursor)
        self.domain_edit_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #221a14;
                color: {Theme.BRASS_LIGHT};
                border: 1px solid {Theme.BRASS_BASE};
                border-radius: 2px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: #36291e;
                border: 1px solid {Theme.BRASS_LIGHT};
                color: #ffffff;
            }}
        """)
        self.domain_edit_btn.clicked.connect(self._edit_selected_domain)
        bar.addWidget(self.domain_edit_btn)

        self.domain_del_btn = QPushButton("🗑  削除")
        self.domain_del_btn.setFixedSize(75, 26)
        self.domain_del_btn.setCursor(Qt.PointingHandCursor)
        self.domain_del_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #2a1515;
                color: #e57373;
                border: 1px solid #5a2525;
                border-radius: 2px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: #441a1a;
                border: 1px solid #d32f2f;
                color: #ffffff;
            }}
        """)
        self.domain_del_btn.clicked.connect(self._delete_selected_domain)
        bar.addWidget(self.domain_del_btn)

        self.domain_reset_btn = QPushButton("🔄  初期値に戻す")
        self.domain_reset_btn.setFixedSize(110, 26)
        self.domain_reset_btn.setCursor(Qt.PointingHandCursor)
        self.domain_reset_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #1a1511;
                color: {Theme.TEXT_MUTED};
                border: 1px solid #4a3a2a;
                border-radius: 2px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: #251d16;
                color: #ffffff;
            }}
        """)
        self.domain_reset_btn.clicked.connect(self._reset_domains_to_default)
        bar.addWidget(self.domain_reset_btn)

        layout.addLayout(bar)

        self.domains_data = dict(app_settings.DEFAULT_DOMAINS)
        return widget

    def _load_domains_table(self):
        """ドメイン一覧をロードしてテーブルに反映"""
        self.domains_data = app_settings.get_domain_mappings()
        self._filter_domains_table()

    def _filter_domains_table(self):
        """検索テキストに基づいてテーブルを更新"""
        if not hasattr(self, "domain_table"):
            return
        query = (self.domain_filter_input.text() if hasattr(self, "domain_filter_input") else "").strip().lower()
        self.domain_table.setRowCount(0)

        items = list(self.domains_data.items())
        items.sort(key=lambda x: x[0])

        visible_count = 0
        for domain, label in items:
            if query and query not in domain.lower() and query not in label.lower():
                continue

            row = self.domain_table.rowCount()
            self.domain_table.insertRow(row)

            item_d = QTableWidgetItem(domain)
            item_d.setData(Qt.UserRole, domain)
            item_d.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)

            item_l = QTableWidgetItem(label)
            item_l.setData(Qt.UserRole, label)
            item_l.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)

            self.domain_table.setItem(row, 0, item_d)
            self.domain_table.setItem(row, 1, item_l)
            visible_count += 1

        if hasattr(self, "domain_count_label"):
            self.domain_count_label.setText(f"登録件数: {len(self.domains_data)} 件 (表示中: {visible_count} 件)")

    def _on_add_domain(self):
        """新規ドメインを追加"""
        raw_d = self.new_domain_input.text().strip()
        label = self.new_domain_label_input.text().strip()

        domain = app_settings.clean_domain(raw_d)
        if not domain:
            QMessageBox.warning(self, "エラー", "有効なドメインを入力してください。\n（例: talto.cc）")
            return
        if not label:
            QMessageBox.warning(self, "エラー", "表示名を入力してください。\n（例: TALTO）")
            return

        self.domains_data[domain] = label
        self.new_domain_input.clear()
        self.new_domain_label_input.clear()
        self._filter_domains_table()

    def _edit_selected_domain(self):
        """選択行のドメインを編集"""
        row = self.domain_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "案内", "編集するドメインを選択してください。")
            return

        item_d = self.domain_table.item(row, 0)
        item_l = self.domain_table.item(row, 1)
        if not item_d or not item_l:
            return

        old_domain = item_d.data(Qt.UserRole)
        old_label = item_l.data(Qt.UserRole)

        dlg = DomainEditDialog(domain=old_domain, label=old_label, parent=self)
        if dlg.exec():
            new_domain = dlg.result_domain
            new_label = dlg.result_label
            if old_domain != new_domain and old_domain in self.domains_data:
                del self.domains_data[old_domain]
            self.domains_data[new_domain] = new_label
            self._filter_domains_table()

    def _delete_selected_domain(self):
        """選択行のドメインを削除"""
        row = self.domain_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "案内", "削除するドメインを選択してください。")
            return

        item_d = self.domain_table.item(row, 0)
        if not item_d:
            return

        domain = item_d.data(Qt.UserRole)
        reply = QMessageBox.question(
            self,
            "削除確認",
            f"ドメイン「{domain}」の表示設定を削除しますか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            if domain in self.domains_data:
                del self.domains_data[domain]
            self._filter_domains_table()

    def _reset_domains_to_default(self):
        """初期値（Booth）にリセット"""
        reply = QMessageBox.question(
            self,
            "初期化確認",
            "ドメイン設定を初期状態（booth.pm = Booth）に戻しますか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.domains_data = dict(app_settings.DEFAULT_DOMAINS)
            self._filter_domains_table()

    def _get_current_domains_from_table(self):
        """現在の辞書データを返す"""
        return getattr(self, "domains_data", dict(app_settings.DEFAULT_DOMAINS))

    def _load_settings(self):
        """設定ファイルから現在の値を読み出して入力欄へ反映"""
        try:
            cfg = app_settings.load()
            self.token_edit.setText(cfg.get("notion_api_key", ""))
            self.db_id_edit.setText(cfg.get("notion_database_id", ""))
            self.api_interval_spin.setValue(
                float(cfg.get("api_request_interval", app_settings.DEFAULT_API_INTERVAL))
            )
            self.notion_limit_spin.setValue(
                int(cfg.get("notion_import_limit", app_settings.DEFAULT_NOTION_IMPORT_LIMIT))
            )
            self.auto_sync_check.setChecked(bool(cfg.get("notion_auto_sync", app_settings.DEFAULT_NOTION_AUTO_SYNC)))
            self.auto_sync_interval_spin.setValue(
                int(cfg.get("notion_auto_sync_interval", app_settings.DEFAULT_NOTION_AUTO_SYNC_INTERVAL))
            )

            shortcuts = cfg.get("shortcuts", {})
            for k, seq_edit in self.shortcut_inputs.items():
                seq_str = shortcuts.get(k, app_settings.DEFAULT_SHORTCUTS.get(k, ""))
                seq_edit.setKeySequence(QKeySequence(seq_str))

            self._load_domains_table()
            self._refresh_backup_stats()
        except Exception as e:
            print(f"Error loading settings: {e}")

    def _reset_shortcuts_to_default(self):
        """ショートカット入力を初期値に戻す"""
        for k, seq_edit in self.shortcut_inputs.items():
            default_str = app_settings.DEFAULT_SHORTCUTS.get(k, "")
            seq_edit.setKeySequence(QKeySequence(default_str))

    def _save_settings(self):
        """入力された設定を settings.ini へ保存"""
        try:
            cfg = app_settings.load()
            cfg["notion_api_key"] = self.token_edit.text().strip()
            cfg["notion_database_id"] = self.db_id_edit.text().strip()
            cfg["api_request_interval"] = round(float(self.api_interval_spin.value()), 2)
            cfg["notion_import_limit"] = int(self.notion_limit_spin.value())
            cfg["notion_auto_sync"] = self.auto_sync_check.isChecked()
            cfg["notion_auto_sync_interval"] = int(self.auto_sync_interval_spin.value())

            shortcuts = {}
            for k, seq_edit in self.shortcut_inputs.items():
                seq = seq_edit.keySequence()
                seq_str = seq.toString() if not seq.isEmpty() else ""
                shortcuts[k] = seq_str
            cfg["shortcuts"] = shortcuts

            cfg["domains"] = self._get_current_domains_from_table()

            app_settings.save(cfg)
            self.settings_saved.emit()
            QMessageBox.information(self, "設定完了", "設定を保存しました。")
            self.accept()
        except Exception as e:
            QMessageBox.warning(self, "エラー", f"保存に失敗しました: {e}")

    # =========================================================================
    # バックアップ・復元タブ
    # =========================================================================
    def _build_backup_tab(self):
        """バックアップ・復元タブを構築"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # 説明ガイド
        guide_txt = (
            "💾 <b>魔導書架の保全と移送 (バックアップ・復元)</b>: 登録されたすべてのシナリオ情報、表紙画像、"
            "タグ、ドメイン設定、セッション冒険録を一括して安全なZipファイルとして書き出し・復元できます。<br>"
            "<span style='color: #a8947f;'>※ PCの移行時や、万が一のデータ破損への備えとしてご活用ください。</span>"
        )
        guide_lbl = QLabel(guide_txt)
        guide_lbl.setStyleSheet("color: #dcd0bd; font-size: 11px; line-height: 1.45;")
        guide_lbl.setWordWrap(True)
        layout.addWidget(guide_lbl)

        layout.addWidget(OrnateDivider(self, height=8))

        # 現在の登録統計表示ボックス
        stats_frame = QFrame()
        stats_frame.setStyleSheet("""
            QFrame {
                background-color: #16120e;
                border: 1px solid #3d2f21;
                border-radius: 4px;
            }
        """)
        sf_layout = QVBoxLayout(stats_frame)
        sf_layout.setContentsMargins(14, 10, 14, 10)
        sf_layout.setSpacing(6)

        sf_title = QLabel("📊  現在の魔導書架 登録データ統計")
        sf_title.setStyleSheet(f"color: {Theme.BRASS_LIGHT}; font-weight: bold; font-size: 12px; border: none;")
        sf_layout.addWidget(sf_title)

        self.backup_stats_lbl = QLabel("読み込み中...")
        self.backup_stats_lbl.setStyleSheet("color: #ffffff; font-size: 12px; border: none;")
        sf_layout.addWidget(self.backup_stats_lbl)

        layout.addWidget(stats_frame)

        # 1. バックアップ作成セクション
        export_box = QFrame()
        export_box.setStyleSheet("""
            QFrame {
                background-color: #17130f;
                border: 1px solid #3d2f21;
                border-radius: 4px;
            }
        """)
        eb_layout = QVBoxLayout(export_box)
        eb_layout.setContentsMargins(14, 12, 14, 12)
        eb_layout.setSpacing(8)

        eb_title = QLabel("📦  書架全体のバックアップを作成 (エクスポート)")
        eb_title.setStyleSheet(f"color: {Theme.BRASS_LIGHT}; font-weight: bold; font-size: 13px; border: none;")
        eb_layout.addWidget(eb_title)

        eb_desc = QLabel("現在のデータベース、表紙画像、タグ、ドメイン設定、冒険録をひとつのZipファイル（.zip）に圧縮して保存します。")
        eb_desc.setStyleSheet("color: #bfa990; font-size: 11px; border: none;")
        eb_desc.setWordWrap(True)
        eb_layout.addWidget(eb_desc)

        eb_btn_bar = QHBoxLayout()
        eb_btn_bar.addStretch()

        self.export_btn = QPushButton("📦  バックアップを書き出す (.zip)")
        self.export_btn.setFixedSize(220, 32)
        self.export_btn.setCursor(Qt.PointingHandCursor)
        self.export_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #2b2014;
                color: {Theme.BRASS_LIGHT};
                border: 1px solid {Theme.BRASS_BASE};
                border-radius: 2px;
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: #3d2d1b;
                border: 1px solid {Theme.BRASS_LIGHT};
                color: #ffffff;
            }}
        """)
        self.export_btn.clicked.connect(self._on_export_backup)
        eb_btn_bar.addWidget(self.export_btn)
        eb_layout.addLayout(eb_btn_bar)

        layout.addWidget(export_box)

        # 2. バックアップ復元セクション
        import_box = QFrame()
        import_box.setStyleSheet("""
            QFrame {
                background-color: #17130f;
                border: 1px solid #3d2f21;
                border-radius: 4px;
            }
        """)
        ib_layout = QVBoxLayout(import_box)
        ib_layout.setContentsMargins(14, 12, 14, 12)
        ib_layout.setSpacing(8)

        ib_title = QLabel("📥  バックアップから復元 (インポート)")
        ib_title.setStyleSheet(f"color: {Theme.BRASS_LIGHT}; font-weight: bold; font-size: 13px; border: none;")
        ib_layout.addWidget(ib_title)

        ib_desc = QLabel("過去に作成したバックアップZipを選択し、書架データを復元します。\n※ 復元直前に現在のデータは安全のため一時自動バックアップされます。")
        ib_desc.setStyleSheet("color: #bfa990; font-size: 11px; border: none;")
        ib_desc.setWordWrap(True)
        ib_layout.addWidget(ib_desc)

        ib_btn_bar = QHBoxLayout()
        ib_btn_bar.addStretch()

        self.import_btn = QPushButton("📥  バックアップから復元する")
        self.import_btn.setFixedSize(200, 32)
        self.import_btn.setCursor(Qt.PointingHandCursor)
        self.import_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #221a14;
                color: #e57373;
                border: 1px solid #5a2525;
                border-radius: 2px;
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: #381a1a;
                border: 1px solid #d32f2f;
                color: #ffffff;
            }}
        """)
        self.import_btn.clicked.connect(self._on_import_backup)
        ib_btn_bar.addWidget(self.import_btn)
        ib_layout.addLayout(ib_btn_bar)

        layout.addWidget(import_box)

        layout.addStretch()
        return widget

    def _refresh_backup_stats(self):
        """現在のDB統計情報を更新"""
        if not hasattr(self, "backup_stats_lbl"):
            return
        from core.backup_manager import BackupManager
        db_path = getattr(self.db, "db_path", "catalog.db") if self.db else "catalog.db"
        stats = BackupManager.get_stats(db_path)
        self.backup_stats_lbl.setText(
            f"📚 登録シナリオ: <b>{stats['item_count']}</b> 冊　｜　"
            f"🏷 タグ: <b>{stats['tag_count']}</b> 種　｜　"
            f"📜 冒険録: <b>{stats['playlog_count']}</b> 件"
        )

    def _on_export_backup(self):
        """バックアップZipの保存ダイアログを開いてエクスポート"""
        from datetime import datetime
        default_filename = f"魔導書架_バックアップ_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        dest_path, _ = QFileDialog.getSaveFileName(
            self,
            "バックアップの保存先を選択",
            default_filename,
            "Zip アーカイブ (*.zip)",
        )
        if not dest_path:
            return

        try:
            from core.backup_manager import BackupManager
            db_path = getattr(self.db, "db_path", "catalog.db") if self.db else "catalog.db"
            settings_path = app_settings.SETTINGS_FILE
            info = BackupManager.create_backup(dest_path, db_path, settings_path)
            stats = info.get("stats", {})
            QMessageBox.information(
                self,
                "バックアップ完了",
                f"書架全体のバックアップを正常に書き出しました！\n\n"
                f"保存先: {dest_path}\n"
                f"シナリオ数: {stats.get('item_count', 0)} 冊\n"
                f"冒険録数: {stats.get('playlog_count', 0)} 件",
            )
        except Exception as e:
            QMessageBox.warning(self, "バックアップ失敗", f"バックアップの作成中にエラーが発生しました:\n{e}")

    def _on_import_backup(self):
        """バックアップZipを選択して復元"""
        zip_path, _ = QFileDialog.getOpenFileName(
            self,
            "復元するバックアップファイルを選択",
            "",
            "Zip アーカイブ (*.zip)",
        )
        if not zip_path:
            return

        try:
            from core.backup_manager import BackupManager
            info = BackupManager.inspect_backup(zip_path)
            stats = info.get("stats", {})
            created_at = info.get("created_at", "不明")

            reply = QMessageBox.warning(
                self,
                "復元の確認",
                f"以下のバックアップデータを復元しますか？\n\n"
                f"作成日時: {created_at}\n"
                f"シナリオ数: {stats.get('item_count', 0)} 冊\n"
                f"冒険録数: {stats.get('playlog_count', 0)} 件\n\n"
                f"※ 現在のデータはすべてこのバックアップで置き換えられます。\n"
                f"（安全のため、現在のデータは .bak として一時保存されます）",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

            db_path = getattr(self.db, "db_path", "catalog.db") if self.db else "catalog.db"
            settings_path = app_settings.SETTINGS_FILE
            BackupManager.restore_backup(zip_path, db_path, settings_path, restore_settings=True)

            self.tags_changed.emit()
            self.settings_saved.emit()
            self._load_settings()
            self._load_tags_table()
            self._refresh_backup_stats()

            QMessageBox.information(
                self,
                "復元完了",
                "バックアップからの復元が正常に完了しました。\n書架のデータが最新のスナップショットに更新されました。",
            )
        except Exception as e:
            QMessageBox.warning(self, "復元失敗", f"復元中にエラーが発生しました:\n{e}")

