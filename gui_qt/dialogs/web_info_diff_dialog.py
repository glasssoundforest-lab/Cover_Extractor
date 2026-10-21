"""Web情報取得時の新旧比較・採否選択ダイアログ (gui_qt/dialogs/web_info_diff_dialog.py)

Webから取得したメタ情報（タイトル、作者、システム、人数、時間、概要、あらすじ、表紙画像等）と
現在の登録情報を左右で対比し、項目ごとに採用するかどうかを選択できる西洋古書調のモーダルダイアログ。
"""

import os
from PySide6.QtCore import Qt, QByteArray
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QCheckBox,
    QScrollArea,
    QWidget,
    QFrame,
    QTextEdit,
    QLineEdit,
    QSizePolicy,
)

from ..theme import Theme
from ..components.ornate import OrnateFrame, OrnateDivider
from ..components.ornate_title_bar import OrnateTitleBar


class WebInfoComparisonDialog(QDialog):
    """取得した情報（Web/Notion等）と現在の情報を比較し、採用する項目を選択するダイアログ"""

    def __init__(
        self,
        current_data: dict,
        web_data: dict,
        parent=None,
        source_name: str = "Web情報",
        db=None,
        item_id=None,
    ):
        super().__init__(parent)
        self.current_data = current_data or {}
        self.web_data = web_data or {}
        self.source_name = source_name or "Web情報"
        self.db = db
        self.item_id = item_id
        self.edited_in_detail = False
        self.checkboxes = {}
        # その場編集用の入力ウィジェット {field_key: (widget, kind)}  kind: "line" / "multi" / "tags"
        self.editors = {}
        self._badges = {}

        src_label = self.source_name.removesuffix("情報")
        self._src_label = src_label
        self.setWindowTitle(f"{src_label}情報比較と採否選択")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        # 縦長のパネル（画面の高さに収まる範囲で最大 960px）
        target_w, target_h = 900, 960
        try:
            from PySide6.QtGui import QGuiApplication
            screen = (parent.screen() if parent is not None and hasattr(parent, "screen") else None) or QGuiApplication.primaryScreen()
            if screen is not None:
                avail = screen.availableGeometry()
                target_h = min(target_h, int(avail.height() * 0.92))
                target_w = min(target_w, int(avail.width() * 0.92))
        except Exception:
            pass
        self.resize(target_w, target_h)
        self.setMinimumSize(720, 600)
        self.setStyleSheet(Theme.get_application_stylesheet())

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # 外枠
        self.frame = OrnateFrame(self, bracket_size=14, bg_color="#181310")
        main_layout.addWidget(self.frame)

        f_layout = QVBoxLayout(self.frame)
        f_layout.setContentsMargins(0, 0, 0, 14)
        f_layout.setSpacing(10)

        # タイトルバー
        self.title_bar = OrnateTitleBar(
            f"❖ 書架同調 ― {src_label}情報比較と採否選択",
            parent=self,
            show_close=True,
        )
        f_layout.addWidget(self.title_bar)

        # 説明ヘッダー & 一括選択ボタンバー
        top_bar = QWidget()
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(18, 4, 18, 0)
        top_layout.setSpacing(10)

        desc_lbl = QLabel(
            f"{self.source_name}から取得した情報と現在の登録内容を比較しました。\n"
            "反映したい項目にチェックを入れ、［✓ 選択した項目を反映］を押してください。\n"
            "右側の取得内容はその場で編集でき、編集した内容がそのまま反映されます。"
        )
        desc_lbl.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 12px; line-height: 1.4;")
        top_layout.addWidget(desc_lbl, 1)

        btn_select_all = QPushButton("すべて選択")
        btn_select_all.setFixedHeight(26)
        btn_select_all.setCursor(Qt.PointingHandCursor)
        btn_select_all.setStyleSheet(f"""
            QPushButton {{
                background-color: #241c14;
                color: {Theme.BRASS_LIGHT};
                border: 1px solid #4a3a2a;
                border-radius: 2px;
                font-size: 11px;
                padding: 0 8px;
            }}
            QPushButton:hover {{
                background-color: #382c1f;
                color: #ffffff;
            }}
        """)
        btn_select_all.clicked.connect(self._select_all)
        top_layout.addWidget(btn_select_all)

        btn_select_diff = QPushButton("変更点のみ選択")
        btn_select_diff.setFixedHeight(26)
        btn_select_diff.setCursor(Qt.PointingHandCursor)
        btn_select_diff.setStyleSheet(f"""
            QPushButton {{
                background-color: #241c14;
                color: {Theme.BRASS_LIGHT};
                border: 1px solid #4a3a2a;
                border-radius: 2px;
                font-size: 11px;
                padding: 0 8px;
            }}
            QPushButton:hover {{
                background-color: #382c1f;
                color: #ffffff;
            }}
        """)
        btn_select_diff.clicked.connect(self._select_changed_only)
        top_layout.addWidget(btn_select_diff)

        btn_deselect_all = QPushButton("すべて解除")
        btn_deselect_all.setFixedHeight(26)
        btn_deselect_all.setCursor(Qt.PointingHandCursor)
        btn_deselect_all.setStyleSheet(f"""
            QPushButton {{
                background-color: #1a1511;
                color: {Theme.TEXT_MUTED};
                border: 1px solid #3d2f22;
                border-radius: 2px;
                font-size: 11px;
                padding: 0 8px;
            }}
            QPushButton:hover {{
                background-color: #281f18;
                color: #ffffff;
            }}
        """)
        btn_deselect_all.clicked.connect(self._deselect_all)
        top_layout.addWidget(btn_deselect_all)

        f_layout.addWidget(top_bar)

        # 区切り線
        div = OrnateDivider(self, height=10)
        f_layout.addWidget(div)

        # スクロールエリア（項目比較リスト）
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
        """)

        scroll_widget = QWidget()
        self.scroll_layout = QVBoxLayout(scroll_widget)
        self.scroll_layout.setContentsMargins(18, 0, 18, 6)
        self.scroll_layout.setSpacing(12)

        # 各項目の比較カードを作成
        self._build_fields_comparison()

        scroll_area.setWidget(scroll_widget)
        f_layout.addWidget(scroll_area, 1)

        # 下部ボタンバー
        bot_div = OrnateDivider(self, height=8)
        f_layout.addWidget(bot_div)

        btn_bar = QHBoxLayout()
        btn_bar.setContentsMargins(18, 0, 18, 4)
        btn_bar.setSpacing(12)

        if self.db and self.item_id:
            self.detail_btn = QPushButton("✏  詳細画面で編集")
            self.detail_btn.setFixedSize(140, 34)
            self.detail_btn.setCursor(Qt.PointingHandCursor)
            self.detail_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #241c14;
                    color: {Theme.BRASS_LIGHT};
                    border: 1px solid #4a3a2a;
                    border-radius: 2px;
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    background-color: #382c1f;
                    color: #ffffff;
                }}
            """)
            self.detail_btn.clicked.connect(self._open_detail_edit_dialog)
            btn_bar.addWidget(self.detail_btn)

        btn_bar.addStretch()

        self.apply_btn = QPushButton("✓  選択した項目を反映")
        self.apply_btn.setFixedSize(170, 34)
        self.apply_btn.setCursor(Qt.PointingHandCursor)
        self.apply_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #5c1818;
                color: #f7e7c4;
                border: 1px solid {Theme.BRASS_LIGHT};
                border-radius: 2px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #7a2020;
                color: #ffffff;
                border-color: #ffda73;
            }}
        """)
        self.apply_btn.clicked.connect(self.accept)
        btn_bar.addWidget(self.apply_btn)

        self.cancel_btn = QPushButton("✕  キャンセル")
        self.cancel_btn.setFixedSize(110, 34)
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
        self.cancel_btn.clicked.connect(self.reject)
        btn_bar.addWidget(self.cancel_btn)

        f_layout.addLayout(btn_bar)

    def _open_detail_edit_dialog(self):
        """詳細編集ダイアログを開き、直接編集・保存できるようにする"""
        from .item_detail_dialog import ItemDetailDialog
        dlg = ItemDetailDialog(self.item_id, self.db, parent=self)
        if dlg.exec() == QDialog.Accepted:
            self.edited_in_detail = True
            self.accept()

    def _build_fields_comparison(self):
        """各メタ情報フィールドの比較カードを構築"""
        # 単一行テキスト項目
        single_line_fields = [
            ("title", "タイトル"),
            ("author", "作者"),
            ("system", "システム"),
            ("players", "プレイ人数"),
            ("duration", "プレイ時間"),
        ]

        for field_key, field_name in single_line_fields:
            curr_val = (self.current_data.get(field_key) or "").strip()
            new_val = (self.web_data.get(field_key) or "").strip()
            self._create_text_diff_card(field_key, field_name, curr_val, new_val)

        # タグ項目
        if "tags" in self.web_data or "tags" in self.current_data:
            self._create_tags_diff_card()

        # 複数行テキスト項目（概要・あらすじ）
        multi_line_fields = [
            ("overview", "概要"),
            ("synopsis", "あらすじ"),
        ]
        for field_key, field_name in multi_line_fields:
            curr_val = (self.current_data.get(field_key) or "").strip()
            new_val = (self.web_data.get(field_key) or "").strip()
            self._create_multiline_diff_card(field_key, field_name, curr_val, new_val)

        # 表紙画像項目
        curr_thumb = self.current_data.get("thumbnail_bytes") or self.current_data.get("thumbnail")
        new_thumb = self.web_data.get("image_bytes") or self.web_data.get("thumbnail_bytes")
        self._create_cover_diff_card(curr_thumb, new_thumb)

    # ------------------------------------------------------------------
    # 共通ヘルパー
    # ------------------------------------------------------------------
    _LINE_EDIT_STYLE = """
        QLineEdit {{
            background-color: #15110d;
            color: {fg};
            border: 1px solid {border};
            border-radius: 2px;
            padding: 4px 6px;
            font-size: 12px;
            selection-background-color: #5c4325;
        }}
        QLineEdit:focus {{
            border: 1px solid #ffda73;
            background-color: #1b1610;
        }}
    """

    _TEXT_EDIT_STYLE = """
        QTextEdit {{
            background-color: {bg};
            color: {fg};
            border: 1px solid {border};
            border-radius: 2px;
            font-size: 12px;
            padding: 6px;
            selection-background-color: #5c4325;
        }}
        QTextEdit:focus {{
            border: 1px solid #ffda73;
        }}
    """

    def _make_card(self, key, is_changed):
        card = QFrame()
        card.setObjectName(f"card_{key}")
        border_col = "#5a452a" if is_changed else "#2d231b"
        bg_col = "#1d1712" if is_changed else "#14100d"
        card.setStyleSheet(f"""
            QFrame#card_{key} {{
                background-color: {bg_col};
                border: 1px solid {border_col};
                border-radius: 4px;
                padding: 6px;
            }}
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)
        return card, layout

    def _make_header(self, key, label, has_new, is_changed, changed_text="● 変更あり"):
        """チェックボックス＋状態バッジのヘッダー行を作成する"""
        h_layout = QHBoxLayout()
        h_layout.setSpacing(8)

        chk = QCheckBox(label)
        chk.setEnabled(has_new)
        chk.setChecked(is_changed)  # 変更がある場合はデフォルトON
        chk.setCursor(Qt.PointingHandCursor)
        chk.setStyleSheet(f"""
            QCheckBox {{
                color: {Theme.BRASS_LIGHT};
                font-size: 13px;
                font-weight: bold;
            }}
            QCheckBox:disabled {{
                color: {Theme.TEXT_MUTED};
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
            }}
        """)
        self.checkboxes[key] = (chk, is_changed)
        h_layout.addWidget(chk)

        badge = QLabel()
        self._badges[key] = badge
        if not has_new:
            badge.setText("（取得データなし）")
            badge.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 11px;")
        elif not is_changed:
            badge.setText("（現在と同一）")
            badge.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 11px;")
        else:
            badge.setText(changed_text)
            badge.setStyleSheet("color: #4ade80; font-size: 11px; font-weight: bold;")
        h_layout.addWidget(badge)
        h_layout.addStretch()
        return h_layout, chk

    def _on_editor_changed(self, key, original_new, current_val):
        """取得内容をその場で編集したとき、チェック状態とバッジを更新する"""
        value = self._editor_value(key)
        chk, _ = self.checkboxes[key]
        badge = self._badges.get(key)
        has_value = bool(value)
        chk.setEnabled(has_value)
        if not has_value:
            chk.setChecked(False)
            if badge:
                badge.setText("（空欄のため反映しません）")
                badge.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 11px;")
            return
        if value != original_new:
            # 手動編集した項目は反映対象として自動でチェック
            chk.setChecked(value != current_val)
            if badge:
                badge.setText("✎ 編集済み")
                badge.setStyleSheet("color: #ffda73; font-size: 11px; font-weight: bold;")
        elif badge:
            if value != current_val:
                badge.setText("● 変更あり")
                badge.setStyleSheet("color: #4ade80; font-size: 11px; font-weight: bold;")
            else:
                badge.setText("（現在と同一）")
                badge.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 11px;")

    def _editor_value(self, key):
        widget, kind = self.editors[key]
        if kind == "multi":
            return widget.toPlainText().strip()
        if kind == "tags":
            return [t.strip() for t in widget.text().replace("、", ",").split(",") if t.strip()]
        return widget.text().strip()

    @staticmethod
    def _small_button(text):
        btn = QPushButton(text)
        btn.setFixedHeight(22)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #1f1812;
                color: {Theme.TEXT_MUTED};
                border: 1px solid #3d2f22;
                border-radius: 2px;
                font-size: 10px;
                padding: 0 6px;
            }}
            QPushButton:hover {{
                background-color: #2c2219;
                color: #ffffff;
            }}
        """)
        return btn

    # ------------------------------------------------------------------
    # 各カード
    # ------------------------------------------------------------------
    def _create_tags_diff_card(self):
        """タグ項目の差分カード（取得側はカンマ区切りでその場編集可能）"""
        key = "tags"

        raw_curr = self.current_data.get("tags") or []
        if isinstance(raw_curr, str):
            curr_tags = [t.strip() for t in raw_curr.split(",") if t.strip()]
        else:
            curr_tags = list(raw_curr)

        raw_new = self.web_data.get("tags") or []
        if isinstance(raw_new, str):
            new_tags = [t.strip() for t in raw_new.split(",") if t.strip()]
        else:
            new_tags = list(raw_new)

        has_new = bool(new_tags)
        is_changed = bool(new_tags) and (set(curr_tags) != set(new_tags))

        card, layout = self._make_card(key, is_changed)
        h_layout, _chk = self._make_header(key, "タグ", has_new, is_changed, changed_text="【変更あり】")
        layout.addLayout(h_layout)

        diff_grid = QGridLayout()
        diff_grid.setContentsMargins(24, 0, 4, 2)
        diff_grid.setHorizontalSpacing(8)
        diff_grid.setVerticalSpacing(4)
        diff_grid.setColumnStretch(1, 1)

        lbl_curr_tag = QLabel("現在:")
        lbl_curr_tag.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 11px;")
        lbl_curr_val = QLabel("、 ".join(curr_tags) if curr_tags else "（なし）")
        lbl_curr_val.setWordWrap(True)
        lbl_curr_val.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lbl_curr_val.setStyleSheet(f"color: {Theme.TEXT_MUTED if not curr_tags else Theme.TEXT_WHITE}; font-size: 12px;")

        lbl_new_tag = QLabel("反映:")
        lbl_new_tag.setStyleSheet(f"color: {Theme.BRASS_LIGHT}; font-size: 11px; font-weight: bold;")
        edit = QLineEdit(", ".join(new_tags))
        edit.setPlaceholderText("カンマ区切りで入力（例: 現代, クローズド, タイマン）")
        edit.setStyleSheet(self._LINE_EDIT_STYLE.format(
            fg=Theme.TEXT_WHITE, border=Theme.BRASS_LIGHT if is_changed else "#33261c"
        ))
        self.editors[key] = (edit, "tags")
        edit.textChanged.connect(lambda _t: self._on_editor_changed(key, new_tags, curr_tags))

        diff_grid.addWidget(lbl_curr_tag, 0, 0)
        diff_grid.addWidget(lbl_curr_val, 0, 1)
        diff_grid.addWidget(lbl_new_tag, 1, 0)
        diff_grid.addWidget(edit, 1, 1)

        layout.addLayout(diff_grid)
        self.scroll_layout.addWidget(card)

    def _create_text_diff_card(self, key, label, curr_val, new_val):
        """単一行項目の差分カード（取得側はその場編集可能）"""
        is_changed = bool(new_val) and (curr_val != new_val)
        has_new = bool(new_val)

        card, layout = self._make_card(key, is_changed)
        h_layout, _chk = self._make_header(key, label, has_new, is_changed)
        layout.addLayout(h_layout)

        diff_grid = QGridLayout()
        diff_grid.setContentsMargins(24, 0, 4, 2)
        diff_grid.setHorizontalSpacing(8)
        diff_grid.setColumnStretch(1, 2)
        diff_grid.setColumnStretch(4, 3)

        lbl_curr_tag = QLabel("現在:")
        lbl_curr_tag.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 11px;")
        lbl_curr_val = QLabel(curr_val or "（未設定）")
        lbl_curr_val.setStyleSheet(f"color: {Theme.TEXT_MUTED if not curr_val else Theme.TEXT_WHITE}; font-size: 12px;")
        lbl_curr_val.setWordWrap(True)
        lbl_curr_val.setTextInteractionFlags(Qt.TextSelectableByMouse)

        arrow = QLabel("➔")
        arrow.setStyleSheet(f"color: {Theme.BRASS_LIGHT if is_changed else Theme.TEXT_MUTED}; font-size: 13px;")

        lbl_new_tag = QLabel("反映:")
        lbl_new_tag.setStyleSheet(f"color: {Theme.BRASS_LIGHT}; font-size: 11px; font-weight: bold;")
        edit = QLineEdit(new_val)
        edit.setPlaceholderText("（取得なし ― 入力すると反映できます）")
        edit.setStyleSheet(self._LINE_EDIT_STYLE.format(
            fg=Theme.BRASS_LIGHT if is_changed else Theme.TEXT_WHITE,
            border=Theme.BRASS_LIGHT if is_changed else "#33261c",
        ))
        self.editors[key] = (edit, "line")
        edit.textChanged.connect(lambda _t: self._on_editor_changed(key, new_val, curr_val))

        diff_grid.addWidget(lbl_curr_tag, 0, 0)
        diff_grid.addWidget(lbl_curr_val, 0, 1)
        diff_grid.addWidget(arrow, 0, 2, Qt.AlignCenter)
        diff_grid.addWidget(lbl_new_tag, 0, 3)
        diff_grid.addWidget(edit, 0, 4)

        layout.addLayout(diff_grid)
        self.scroll_layout.addWidget(card)

    def _create_multiline_diff_card(self, key, label, curr_val, new_val):
        """概要・あらすじなどの複数行テキスト差分カード（左: 現在 / 右: その場編集できる大きな入力欄）"""
        is_changed = bool(new_val) and (curr_val != new_val)
        has_new = bool(new_val)

        card, layout = self._make_card(key, is_changed)
        h_layout, _chk = self._make_header(key, label, has_new, is_changed)

        # 編集補助ボタン
        btn_use_curr = self._small_button("← 現在の内容を読み込む")
        btn_use_curr.setToolTip("現在の登録内容を右の編集欄にコピーして、それを元に編集します")
        btn_reset = self._small_button("↺ 取得内容に戻す")
        btn_reset.setToolTip("右の編集欄を取得した内容に戻します")
        h_layout.addWidget(btn_use_curr)
        h_layout.addWidget(btn_reset)
        layout.addLayout(h_layout)

        # 概要・あらすじは大きく取って編集しやすくする
        edit_height = 260 if key == "synopsis" else 220

        columns_layout = QHBoxLayout()
        columns_layout.setContentsMargins(24, 0, 4, 4)
        columns_layout.setSpacing(10)

        # 左: 現在の情報（参照用・読み取り専用）
        left_box = QVBoxLayout()
        left_box.setSpacing(3)
        left_lbl = QLabel("現在の登録内容:")
        left_lbl.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 11px;")
        left_box.addWidget(left_lbl)

        txt_curr = QTextEdit()
        txt_curr.setReadOnly(True)
        txt_curr.setPlainText(curr_val or "（未設定）")
        txt_curr.setMinimumHeight(edit_height)
        txt_curr.setStyleSheet(self._TEXT_EDIT_STYLE.format(
            bg="#120e0b", fg=Theme.TEXT_MUTED if not curr_val else "#b8a78f", border="#2a2018"
        ))
        left_box.addWidget(txt_curr)
        columns_layout.addLayout(left_box, 2)

        arrow = QLabel("➔")
        arrow.setStyleSheet(f"color: {Theme.BRASS_LIGHT if is_changed else Theme.TEXT_MUTED}; font-size: 15px;")
        columns_layout.addWidget(arrow, 0, Qt.AlignCenter)

        # 右: 反映する内容（その場編集可能）
        right_box = QVBoxLayout()
        right_box.setSpacing(3)
        right_lbl = QLabel(f"反映する内容（{self._src_label}から取得・編集可）:")
        right_lbl.setStyleSheet(f"color: {Theme.BRASS_LIGHT}; font-size: 11px; font-weight: bold;")
        right_box.addWidget(right_lbl)

        txt_new = QTextEdit()
        txt_new.setAcceptRichText(False)
        txt_new.setPlainText(new_val)
        txt_new.setPlaceholderText("（取得なし ― 入力すると反映できます）")
        txt_new.setMinimumHeight(edit_height)
        txt_new.setStyleSheet(self._TEXT_EDIT_STYLE.format(
            bg="#17120e", fg=Theme.TEXT_WHITE, border=Theme.BRASS_LIGHT if is_changed else "#4a3a2a"
        ))
        self.editors[key] = (txt_new, "multi")
        txt_new.textChanged.connect(lambda: self._on_editor_changed(key, new_val, curr_val))
        right_box.addWidget(txt_new)
        columns_layout.addLayout(right_box, 3)

        btn_use_curr.clicked.connect(lambda: txt_new.setPlainText(curr_val))
        btn_use_curr.setEnabled(bool(curr_val))
        btn_reset.clicked.connect(lambda: txt_new.setPlainText(new_val))

        layout.addLayout(columns_layout)
        self.scroll_layout.addWidget(card)

    def _create_cover_diff_card(self, curr_bytes, new_bytes):
        """表紙画像の差分プレビューカード"""
        key = "cover"
        card = QFrame()
        card.setObjectName(f"card_{key}")
        has_new = bool(new_bytes)
        is_changed = has_new and (curr_bytes != new_bytes)

        border_col = "#5a452a" if is_changed else "#2d231b"
        bg_col = "#1d1712" if is_changed else "#14100d"
        card.setStyleSheet(f"""
            QFrame#card_{key} {{
                background-color: {bg_col};
                border: 1px solid {border_col};
                border-radius: 4px;
                padding: 6px;
            }}
        """)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        # ヘッダー行
        h_layout = QHBoxLayout()
        h_layout.setSpacing(8)

        chk = QCheckBox("表紙画像")
        chk.setEnabled(has_new)
        chk.setChecked(is_changed)
        chk.setCursor(Qt.PointingHandCursor if has_new else Qt.ArrowCursor)
        chk.setStyleSheet(f"""
            QCheckBox {{
                color: {Theme.BRASS_LIGHT if has_new else Theme.TEXT_MUTED};
                font-size: 13px;
                font-weight: bold;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
            }}
        """)
        self.checkboxes[key] = (chk, is_changed)
        h_layout.addWidget(chk)

        if not has_new:
            badge = QLabel("（取得データなし）")
            badge.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 11px;")
            h_layout.addWidget(badge)
        elif not is_changed:
            badge = QLabel("（現在と同一）")
            badge.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 11px;")
            h_layout.addWidget(badge)
        else:
            badge = QLabel("● 新しい表紙あり")
            badge.setStyleSheet("color: #4ade80; font-size: 11px; font-weight: bold;")
            h_layout.addWidget(badge)

        h_layout.addStretch()
        layout.addLayout(h_layout)

        # プレビュー横並び
        img_row = QHBoxLayout()
        img_row.setContentsMargins(24, 0, 4, 4)
        img_row.setSpacing(16)

        # 現在の画像
        left_v = QVBoxLayout()
        left_v.setSpacing(4)
        left_v.addWidget(QLabel("現在の表紙:"))
        lbl_curr_img = QLabel()
        lbl_curr_img.setFixedSize(110, 80)
        lbl_curr_img.setAlignment(Qt.AlignCenter)
        lbl_curr_img.setStyleSheet("background-color: #120e0b; border: 1px solid #33261c;")
        if curr_bytes:
            pix = QPixmap()
            if pix.loadFromData(QByteArray(curr_bytes)):
                lbl_curr_img.setPixmap(pix.scaled(110, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                lbl_curr_img.setText("画像無効")
        else:
            lbl_curr_img.setText("なし")
            lbl_curr_img.setStyleSheet("background-color: #120e0b; border: 1px solid #33261c; color: #73604d; font-size: 10px;")
        left_v.addWidget(lbl_curr_img)
        img_row.addLayout(left_v)

        arrow = QLabel("➔")
        arrow.setStyleSheet(f"color: {Theme.BRASS_LIGHT if is_changed else Theme.TEXT_MUTED}; font-size: 16px;")
        img_row.addWidget(arrow, 0, Qt.AlignCenter)

        # 取得した画像
        right_v = QVBoxLayout()
        right_v.setSpacing(4)
        lbl_right_title = QLabel("Webから取得した表紙:")
        lbl_right_title.setStyleSheet(f"color: {Theme.BRASS_LIGHT if has_new else Theme.TEXT_MUTED}; font-weight: bold;")
        right_v.addWidget(lbl_right_title)

        lbl_new_img = QLabel()
        lbl_new_img.setFixedSize(110, 80)
        lbl_new_img.setAlignment(Qt.AlignCenter)
        border_col = Theme.BRASS_LIGHT if is_changed else "#33261c"
        lbl_new_img.setStyleSheet(f"background-color: #15110d; border: 1px solid {border_col};")
        if new_bytes:
            pix = QPixmap()
            if pix.loadFromData(QByteArray(new_bytes)):
                lbl_new_img.setPixmap(pix.scaled(110, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                lbl_new_img.setText("画像無効")
        else:
            lbl_new_img.setText("なし")
            lbl_new_img.setStyleSheet("background-color: #15110d; border: 1px solid #33261c; color: #73604d; font-size: 10px;")
        right_v.addWidget(lbl_new_img)
        img_row.addLayout(right_v)

        img_row.addStretch()
        layout.addLayout(img_row)
        self.scroll_layout.addWidget(card)

    def _select_all(self):
        """取得データが存在するすべての項目を選択"""
        for key, (chk, _) in self.checkboxes.items():
            if chk.isEnabled():
                chk.setChecked(True)

    def _select_changed_only(self):
        """変更がある項目のみを選択"""
        for key, (chk, is_changed) in self.checkboxes.items():
            if chk.isEnabled():
                chk.setChecked(is_changed)

    def _deselect_all(self):
        """すべての選択を解除"""
        for key, (chk, _) in self.checkboxes.items():
            if chk.isEnabled():
                chk.setChecked(False)

    def get_selected_fields(self) -> set[str]:
        """ユーザーが採用（チェック）したフィールドのキー集合を返す"""
        selected = set()
        for key, (chk, _) in self.checkboxes.items():
            if chk.isChecked():
                selected.add(key)
        return selected

    def get_edited_values(self) -> dict:
        """その場編集後の各項目の値を返す（キー: title/author/system/players/duration/overview/synopsis/tags）"""
        return {key: self._editor_value(key) for key in self.editors}

    def accept(self):
        """反映時、その場編集した値を取得データ（web_data）へ書き戻してから閉じる"""
        if not self.edited_in_detail:
            for key, value in self.get_edited_values().items():
                if value:
                    self.web_data[key] = value
        super().accept()
