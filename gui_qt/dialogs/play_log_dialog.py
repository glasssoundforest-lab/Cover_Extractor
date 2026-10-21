"""セッション記録（冒険録）追加・編集ダイアログ (gui_qt/dialogs/play_log_dialog.py)

TRPGのプレイ日、役割（GM/PL）、卓メンバー、使用キャラクター、結果（生還/ロスト）、
セッションメモを西洋古書調のUIで記録・編集します。
"""

from datetime import date
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QPushButton,
    QComboBox,
    QMessageBox,
    QWidget,
)

from ..theme import Theme
from ..components.ornate import OrnateFrame, OrnateDivider
from ..components.ornate_title_bar import OrnateTitleBar


class PlayLogEditDialog(QDialog):
    """西洋古書調のセッション履歴（冒険録）編集ダイアログ"""

    def __init__(self, log_data=None, parent=None):
        super().__init__(parent)
        self.log_data = log_data or {}
        self.is_edit = bool(log_data and log_data.get("id"))
        title_text = "冒険録の編集" if self.is_edit else "新たな冒険録を記す"

        self.setWindowTitle(title_text)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.resize(520, 560)
        self.setStyleSheet(Theme.get_application_stylesheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.frame = OrnateFrame(self, bracket_size=14, bg_color="#181310")
        layout.addWidget(self.frame)

        f_layout = QVBoxLayout(self.frame)
        f_layout.setContentsMargins(0, 0, 0, 14)
        f_layout.setSpacing(10)

        # 画面デザイン一体型タイトルバー
        self.title_bar = OrnateTitleBar(title_text, parent=self, show_close=True)
        f_layout.addWidget(self.title_bar)

        content_widget = QWidget()
        c_layout = QVBoxLayout(content_widget)
        c_layout.setContentsMargins(16, 4, 16, 0)
        c_layout.setSpacing(10)
        f_layout.addWidget(content_widget)

        grid = QGridLayout()
        grid.setSpacing(8)
        grid.setColumnStretch(1, 1)

        # 1. プレイ日
        lbl_date = QLabel("プレイ日:")
        lbl_date.setStyleSheet(f"color: {Theme.TEXT_WHITE}; font-size: 12px; font-weight: bold;")
        grid.addWidget(lbl_date, 0, 0)

        self.date_edit = QLineEdit(self.log_data.get("session_date") or date.today().isoformat())
        self.date_edit.setPlaceholderText("YYYY-MM-DD (例: 2026-10-17)")
        self.date_edit.setFixedHeight(28)
        self.date_edit.setStyleSheet(self._input_style())
        grid.addWidget(self.date_edit, 0, 1)

        # 2. 役割（GM / PL / 観戦）
        lbl_role = QLabel("役割 (立ち位置):")
        lbl_role.setStyleSheet(f"color: {Theme.TEXT_WHITE}; font-size: 12px; font-weight: bold;")
        grid.addWidget(lbl_role, 1, 0)

        self.role_combo = QComboBox()
        self.role_combo.setEditable(True)
        self.role_combo.addItems(["PL (プレイヤー)", "KP / GM (ゲームマスター)", "観戦 / サブGM", "ソロプレイ"])
        current_role = self.log_data.get("role") or "PL (プレイヤー)"
        # 既存値のマッチングまたはセット
        idx = self.role_combo.findText(current_role)
        if idx >= 0:
            self.role_combo.setCurrentIndex(idx)
        else:
            self.role_combo.setEditText(current_role)
        self.role_combo.setFixedHeight(28)
        self.role_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: #191410;
                color: #ffffff;
                border: 1px solid {Theme.BRASS_BASE};
                border-radius: 2px;
                padding: 2px 6px;
                font-size: 12px;
            }}
            QComboBox:focus {{
                border: 1px solid {Theme.BRASS_LIGHT};
            }}
            QComboBox QAbstractItemView {{
                background-color: #1c1510;
                color: #ffffff;
                selection-background-color: #3b2c1d;
                border: 1px solid #3d2f21;
            }}
        """)
        grid.addWidget(self.role_combo, 1, 1)

        # 3. 使用キャラクター名
        lbl_char = QLabel("使用キャラクター:")
        lbl_char.setStyleSheet(f"color: {Theme.TEXT_WHITE}; font-size: 12px; font-weight: bold;")
        grid.addWidget(lbl_char, 2, 0)

        self.char_edit = QLineEdit(self.log_data.get("character_name") or "")
        self.char_edit.setPlaceholderText("例: 御手洗 清十郎 (私立探偵)")
        self.char_edit.setFixedHeight(28)
        self.char_edit.setStyleSheet(self._input_style())
        grid.addWidget(self.char_edit, 2, 1)

        # 4. 結果 / 結末
        lbl_res = QLabel("結果 / 結末:")
        lbl_res.setStyleSheet(f"color: {Theme.TEXT_WHITE}; font-size: 12px; font-weight: bold;")
        grid.addWidget(lbl_res, 3, 0)

        res_box = QHBoxLayout()
        self.res_edit = QLineEdit(self.log_data.get("result") or "")
        self.res_edit.setPlaceholderText("例: 生還 / ロスト / END-A / トゥルーエンド")
        self.res_edit.setFixedHeight(28)
        self.res_edit.setStyleSheet(self._input_style())
        res_box.addWidget(self.res_edit)

        # 簡易プリセットボタン
        for preset, color in [("生還", "#2e7d32"), ("ロスト", "#c62828"), ("END-A", "#b3882a")]:
            p_btn = QPushButton(preset)
            p_btn.setFixedSize(50, 26)
            p_btn.setCursor(Qt.PointingHandCursor)
            p_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #1a1511;
                    color: {color};
                    border: 1px solid {color};
                    border-radius: 2px;
                    font-size: 11px;
                }}
                QPushButton:hover {{
                    background-color: {color};
                    color: #ffffff;
                }}
            """)
            p_btn.clicked.connect(lambda _, t=preset: self.res_edit.setText(t))
            res_box.addWidget(p_btn)

        grid.addLayout(res_box, 3, 1)

        # 5. 参加メンバー
        lbl_members = QLabel("卓メンバー:")
        lbl_members.setStyleSheet(f"color: {Theme.TEXT_WHITE}; font-size: 12px; font-weight: bold;")
        grid.addWidget(lbl_members, 4, 0)

        self.members_edit = QLineEdit(self.log_data.get("party_members") or "")
        self.members_edit.setPlaceholderText("例: Aさん(KP), Bさん, Cさん")
        self.members_edit.setFixedHeight(28)
        self.members_edit.setStyleSheet(self._input_style())
        grid.addWidget(self.members_edit, 4, 1)

        c_layout.addLayout(grid)

        # 6. セッションメモ / 感想
        lbl_memo = QLabel("冒険の記録 / メモ・感想:")
        lbl_memo.setStyleSheet(f"color: {Theme.TEXT_WHITE}; font-size: 12px; font-weight: bold;")
        c_layout.addWidget(lbl_memo)

        self.memo_edit = QTextEdit()
        self.memo_edit.setPlaceholderText("セッション中の名場面やダイス目、感想、秘密のメモなど...")
        self.memo_edit.setPlainText(self.log_data.get("memo") or "")
        self.memo_edit.setStyleSheet(f"""
            QTextEdit {{
                background-color: #191410;
                color: #ffffff;
                border: 1px solid {Theme.BRASS_BASE};
                border-radius: 2px;
                padding: 6px;
                font-size: 12px;
                line-height: 1.4;
            }}
            QTextEdit:focus {{
                border: 1px solid {Theme.BRASS_LIGHT};
            }}
        """)
        c_layout.addWidget(self.memo_edit)

        c_layout.addSpacing(6)

        # ボタンバー
        btn_bar = QHBoxLayout()
        btn_bar.addStretch()

        save_btn = QPushButton("💾 冒険録を保存")
        save_btn.setFixedSize(125, 30)
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

    def _input_style(self):
        return f"""
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
        """

    def _on_save(self):
        s_date = self.date_edit.text().strip()
        role = self.role_combo.currentText().strip()
        char_name = self.char_edit.text().strip()
        result = self.res_edit.text().strip()
        members = self.members_edit.text().strip()
        memo = self.memo_edit.toPlainText().strip()

        if not s_date and not char_name and not memo and not result:
            QMessageBox.warning(self, "エラー", "プレイ日またはメモ、キャラクター名などを入力してください。")
            return

        self.result_data = {
            "session_date": s_date,
            "role": role,
            "character_name": char_name,
            "result": result,
            "party_members": members,
            "memo": memo,
        }
        self.accept()
