"""西洋古書調のカスタムタイトルバー (gui_qt/components/ornate_title_bar.py)

OS標準の無骨なタイトルバーを排し、魔導書架の画面デザインの一部として美しく一体化するタイトルバー。
真鍮金具、フロール・デ・リス、セリフフォント、ウィンドウドラッグ移動、最小化・最大化・閉じるボタンを提供します。
"""

from PySide6.QtCore import Qt, QPoint, Signal, QEvent
from PySide6.QtGui import QColor, QPainter, QPen, QBrush
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QApplication,
)

from ..theme import Theme
from .ornate import OrnateDivider, make_fleur_pixmap


class OrnateTitleBar(QWidget):
    """西洋アンティーク調の画面デザイン一体型タイトルバー"""
    close_clicked = Signal()

    def __init__(self, title_text="魔導書架", parent=None, show_minimize=False, show_maximize=False, show_close=True):
        super().__init__(parent)
        self.target_window = parent or self.window()
        self._drag_pos = None
        self.setFixedHeight(34)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 8, 0)
        layout.setSpacing(10)

        # 1. 百合の紋章アイコン
        fleur = QLabel()
        fleur.setPixmap(make_fleur_pixmap(14, Theme.BRASS_LIGHT))
        fleur.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(fleur)

        # 2. タイトル文字列
        self.title_label = QLabel(title_text)
        self.title_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.title_label.setStyleSheet(f"""
            color: {Theme.BRASS_LIGHT};
            font-family: {Theme.FONT_SERIF};
            font-size: 13px;
            font-weight: bold;
            background: transparent;
        """)
        layout.addWidget(self.title_label)

        # 3. アンティーク真鍮の仕切りライン（右側のボタン群へ伸びる）
        divider = OrnateDivider(self, height=8)
        divider.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(divider, 1)

        # 4. 操作ボタン群
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)

        if show_minimize:
            self.min_btn = QPushButton("─")
            self.min_btn.setFixedSize(36, 26)
            self.min_btn.setToolTip("最小化")
            self.min_btn.setCursor(Qt.PointingHandCursor)
            self.min_btn.setStyleSheet(self._btn_style())
            self.min_btn.clicked.connect(self._minimize_window)
            btn_layout.addWidget(self.min_btn)

        if show_maximize:
            self.max_btn = QPushButton("□")
            self.max_btn.setFixedSize(36, 26)
            self.max_btn.setToolTip("最大化 / 元に戻す")
            self.max_btn.setCursor(Qt.PointingHandCursor)
            self.max_btn.setStyleSheet(self._btn_style())
            self.max_btn.clicked.connect(self._toggle_maximize_window)
            btn_layout.addWidget(self.max_btn)

        if show_close:
            self.close_btn = QPushButton("✕")
            self.close_btn.setFixedSize(36, 26)
            self.close_btn.setToolTip("閉じる")
            self.close_btn.setCursor(Qt.PointingHandCursor)
            self.close_btn.setStyleSheet(self._close_btn_style())
            self.close_btn.clicked.connect(self._close_window)
            btn_layout.addWidget(self.close_btn)

        layout.addLayout(btn_layout)

        self.setStyleSheet(f"""
            OrnateTitleBar {{
                background-color: #120e0b;
                border-bottom: 1px solid #3d2f21;
            }}
        """)

    def _btn_style(self):
        return f"""
            QPushButton {{
                background-color: #201912;
                color: #f7dfa5;
                border: 1px solid #5a432d;
                border-radius: 3px;
                font-size: 13px;
                font-weight: bold;
                font-family: {Theme.FONT_SERIF};
            }}
            QPushButton:hover {{
                background-color: #4a3725;
                border: 1px solid #ffd88a;
                color: #ffffff;
            }}
            QPushButton:pressed {{
                background-color: #140f0b;
            }}
        """

    def _close_btn_style(self):
        return f"""
            QPushButton {{
                background-color: #381617;
                color: #ffc2c2;
                border: 1px solid #8e3538;
                border-radius: 3px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #b32429;
                border: 1px solid #ff5c5c;
                color: #ffffff;
            }}
            QPushButton:pressed {{
                background-color: #631215;
            }}
        """

    def setTitle(self, text):
        self.title_label.setText(text)

    def _minimize_window(self):
        win = self.target_window or self.window()
        win.showMinimized()

    def _toggle_maximize_window(self):
        win = self.target_window or self.window()
        if win.isMaximized():
            win.showNormal()
            if hasattr(self, "max_btn"):
                self.max_btn.setText("□")
        else:
            win.showMaximized()
            if hasattr(self, "max_btn"):
                self.max_btn.setText("❐")

    def _close_window(self):
        self.close_clicked.emit()
        win = self.target_window or self.window()
        if hasattr(win, "reject"):
            win.reject()
        else:
            win.close()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            win = self.target_window or self.window()
            if win.isMaximized():
                win.showNormal()
                if hasattr(self, "max_btn"):
                    self.max_btn.setText("□")
            global_p = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
            self._drag_pos = global_p - win.pos()
            # OSネイティブの滑らかな移動APIを試行
            handle = win.windowHandle()
            if handle and hasattr(handle, "startSystemMove"):
                handle.startSystemMove()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            win = self.target_window or self.window()
            if not win.isMaximized():
                global_p = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
                win.move(global_p - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def mouseDoubleClickEvent(self, event):
        if hasattr(self, "max_btn"):
            self._toggle_maximize_window()
