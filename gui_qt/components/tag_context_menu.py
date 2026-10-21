"""アンティーク調の複数タグ選択＆コンテキストメニュー (gui_qt/components/tag_context_menu.py)

ユーザー要望に対応:
- 右クリックで出現し、タグを一個ずつではなく複数同時にチェック可能
- クリックしてもメニューは閉じず連続してON/OFF可能
- 欄外をクリックした際に、チェックされた内容がデータベースに自動反映される
- 「本を開く」「ファイルの場所を開く」「削除」「新規タグ追加」も統合
"""

import os
import sys
import subprocess
from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QCursor, QAction, QPainter, QPen, QBrush, QPixmap, QColor
from PySide6.QtWidgets import (
    QMenu,
    QWidgetAction,
    QWidget,
    QHBoxLayout,
    QCheckBox,
    QLabel,
    QInputDialog,
    QMessageBox,
)

from ..theme import Theme
from .ornate import make_fleur_pixmap


def make_tag_color_pixmap(color_hex, size=12):
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(Theme.BRASS_LIGHT), 1))
    p.setBrush(QBrush(QColor(color_hex or "#546e7a")))
    p.drawEllipse(1, 1, size - 2, size - 2)
    p.end()
    return pix


class TagCheckWidget(QWidget):
    """メニュー内に埋め込む真鍮調チェックボックス付きタグ行（カラーサークル付き）"""
    def __init__(self, tag_id, tag_name, color=None, is_checked=False, parent=None):
        super().__init__(parent)
        self.tag_id = tag_id
        self.tag_name = tag_name

        self.setFixedHeight(28)
        self.setCursor(Qt.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 2, 16, 2)
        layout.setSpacing(8)

        # カラーサークル
        col_lbl = QLabel()
        col_lbl.setPixmap(make_tag_color_pixmap(color, size=12))
        col_lbl.setFixedSize(14, 14)
        col_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(col_lbl)

        self.checkbox = QCheckBox(tag_name)
        self.checkbox.setChecked(is_checked)
        self.checkbox.setCursor(Qt.PointingHandCursor)
        self.checkbox.setStyleSheet(f"""
            QCheckBox {{
                color: {Theme.TEXT_WHITE};
                font-size: 12px;
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
                image: none;
            }}
        """)
        layout.addWidget(self.checkbox)

        # ウィジェット全体をクリックしてもチェックがトグルするようにする
        self.setStyleSheet("""
            TagCheckWidget:hover {
                background-color: #251d16;
            }
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.checkbox.toggle()
            event.accept()
            return
        super().mousePressEvent(event)

    def is_checked(self):
        return self.checkbox.isChecked()


class ScenarioContextMenu(QMenu):
    """シナリオカード用の西洋古書調コンテキストメニュー"""
    tags_updated = Signal(int)          # item_id
    open_detail_requested = Signal(int) # item_id
    delete_requested = Signal(int)      # item_id
    favorite_toggled = Signal(int, bool)# item_id, is_favorite
    bookmark_toggled = Signal(int, bool)# item_id, is_bookmarked

    def __init__(self, item_id, db, parent=None):
        super().__init__(parent)
        self.item_id = item_id
        self.db = db
        self.item_data = self.db.get_item(item_id)
        self.is_favorite = bool(self.db.get_favorite(item_id))
        self.is_bookmarked = bool(self.db.get_bookmarked(item_id))
        self.tag_widgets = {}

        self._build_menu()

    def _build_menu(self):
        # 1. 本を開く
        act_open = QAction("✦  本を開く (詳細・あらすじ編集)", self)
        act_open.triggered.connect(lambda: self.open_detail_requested.emit(self.item_id))
        self.addAction(act_open)

        # 2. お気に入り切り替え
        fav_text = "★  お気に入りから解除" if self.is_favorite else "☆  お気に入りに追加"
        act_fav = QAction(fav_text, self)
        act_fav.triggered.connect(self._toggle_favorite)
        self.addAction(act_fav)

        # 3. しおり切り替え（しおりを挟む／しおりを外す）
        bm_text = "🔖  しおりを外す" if self.is_bookmarked else "🔖  しおりを挟む"
        act_bm = QAction(bm_text, self)
        act_bm.triggered.connect(self._toggle_bookmarked)
        self.addAction(act_bm)

        # 4. ファイルの場所を開く
        if self.item_data and self.item_data[1] and os.path.exists(self.item_data[1]):
            act_reveal = QAction("📁  ファイルの場所を開く", self)
            act_reveal.triggered.connect(self._reveal_file)
            self.addAction(act_reveal)

        self.addSeparator()

        # 3. グローバルタグ見出し
        head_act = QAction("🌐  グローバルタグ設定 (複数選択可)", self)
        head_act.setEnabled(False)
        self.addAction(head_act)

        # 4. グローバルタグ一覧（CoC、マダミス、未通過、通過済、GM可 等）
        global_tags = self.db.get_global_tags()
        current_tags = {t[0] for t in self.db.get_item_tags(self.item_id, is_global=True)}

        for tag_tuple in global_tags:
            tid = tag_tuple[0]
            tname = tag_tuple[1]
            tcolor = tag_tuple[2] if len(tag_tuple) > 2 else None
            w = TagCheckWidget(tid, tname, color=tcolor, is_checked=(tid in current_tags), parent=self)
            action = QWidgetAction(self)
            action.setDefaultWidget(w)
            self.addAction(action)
            self.tag_widgets[tid] = w

        self.addSeparator()

        # 5. シナリオ削除
        act_del = QAction("🗑  書架から除籍 (削除)...", self)
        act_del.triggered.connect(lambda: self.delete_requested.emit(self.item_id))
        self.addAction(act_del)

        # メニューが閉じた時（欄外クリック時含む）に、チェック状態をDBに保存
        self.aboutToHide.connect(self._apply_tag_changes)

    def _reveal_file(self):
        file_path = self.item_data[1]
        if not file_path or not isinstance(file_path, str):
            return
        # 制御文字・NULLバイト混入の防御
        if any(c in file_path for c in "\x00\r\n"):
            print("Security warning: Invalid characters in file_path")
            return
        try:
            norm_path = os.path.normpath(os.path.abspath(file_path))
            if os.name == "nt":
                # リスト形式で安全に渡す（シェルのメタ文字展開・コマンド分割を防止）
                if os.path.exists(norm_path):
                    subprocess.Popen(["explorer.exe", f"/select,{norm_path}"])
                else:
                    folder = os.path.dirname(norm_path)
                    if os.path.exists(folder):
                        subprocess.Popen(["explorer.exe", folder])
            elif sys.platform == "darwin":
                if os.path.exists(norm_path):
                    subprocess.Popen(["open", "-R", norm_path])
                else:
                    folder = os.path.dirname(norm_path)
                    if os.path.exists(folder):
                        subprocess.Popen(["open", folder])
            else:
                folder = norm_path if os.path.isdir(norm_path) else os.path.dirname(norm_path)
                if os.path.exists(folder):
                    subprocess.Popen(["xdg-open", folder])
        except Exception as e:
            print(f"Error revealing file: {e}")

    def _toggle_favorite(self):
        new_fav = not self.is_favorite
        self.db.set_favorite(self.item_id, new_fav)
        self.favorite_toggled.emit(self.item_id, new_fav)

    def _toggle_bookmarked(self):
        new_bm = not self.is_bookmarked
        self.db.set_bookmarked(self.item_id, new_bm)
        self.bookmark_toggled.emit(self.item_id, new_bm)

    def _apply_tag_changes(self):
        """メニューが閉じる際にグローバルタグのチェック状態を反映（ローカルタグは保護・維持）"""
        if not self.tag_widgets:
            return

        new_selected_global_ids = {
            tid for tid, widget in self.tag_widgets.items()
            if widget.is_checked()
        }

        # 既存のグローバルタグとローカルタグを取得
        current_global_ids = {t[0] for t in self.db.get_item_tags(self.item_id, is_global=True)}
        current_local_ids = {t[0] for t in self.db.get_item_tags(self.item_id, is_global=False)}

        # グローバルタグに変更があった場合のみDBを更新
        if current_global_ids != new_selected_global_ids:
            all_tag_ids = list(current_local_ids | new_selected_global_ids)
            self.db.set_item_tags(self.item_id, all_tag_ids)
            self.tags_updated.emit(self.item_id)
