"""装飾コンポーネントモジュール (gui_qt/components/ornate.py)

西洋古書・グリモワール調の真鍮装飾フレーム、金具、百合紋章、
区切り線、ピルタグ等の再利用可能なウィジェット群を提供します。
"""

from PySide6.QtCore import Qt, QPoint, QSize, Signal, QRect
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QPolygon, QPixmap, QFont
from PySide6.QtWidgets import QWidget, QFrame, QHBoxLayout, QLabel, QLayout

from ..theme import Theme


def make_fleur_pixmap(size=18, color=Theme.BRASS_LIGHT):
    """西洋アンティーク調のフルール・ド・リス（百合紋章）アイコンを生成"""
    scale = 4
    S = size * scale
    pix = QPixmap(S, S)
    pix.fill(Qt.transparent)

    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(color))

    cx, cy = S / 2.0, S / 2.0

    # 中央の花弁
    pts_center = [
        QPoint(int(cx), int(cy - S * 0.44)),
        QPoint(int(cx + S * 0.12), int(cy - S * 0.10)),
        QPoint(int(cx + S * 0.08), int(cy + S * 0.15)),
        QPoint(int(cx), int(cy + S * 0.10)),
        QPoint(int(cx - S * 0.08), int(cy + S * 0.15)),
        QPoint(int(cx - S * 0.12), int(cy - S * 0.10)),
    ]
    painter.drawPolygon(QPolygon(pts_center))

    # 左の花弁
    pts_left = [
        QPoint(int(cx - S * 0.06), int(cy + S * 0.05)),
        QPoint(int(cx - S * 0.28), int(cy - S * 0.15)),
        QPoint(int(cx - S * 0.40), int(cy - S * 0.02)),
        QPoint(int(cx - S * 0.28), int(cy + S * 0.20)),
        QPoint(int(cx - S * 0.06), int(cy + S * 0.14)),
    ]
    painter.drawPolygon(QPolygon(pts_left))

    # 右の花弁
    pts_right = [
        QPoint(int(cx + S * 0.06), int(cy + S * 0.05)),
        QPoint(int(cx + S * 0.28), int(cy - S * 0.15)),
        QPoint(int(cx + S * 0.40), int(cy - S * 0.02)),
        QPoint(int(cx + S * 0.28), int(cy + S * 0.20)),
        QPoint(int(cx + S * 0.06), int(cy + S * 0.14)),
    ]
    painter.drawPolygon(QPolygon(pts_right))

    # 根元の結束飾り
    pts_base = [
        QPoint(int(cx - S * 0.16), int(cy + S * 0.14)),
        QPoint(int(cx + S * 0.16), int(cy + S * 0.14)),
        QPoint(int(cx + S * 0.08), int(cy + S * 0.36)),
        QPoint(int(cx), int(cy + S * 0.44)),
        QPoint(int(cx - S * 0.08), int(cy + S * 0.36)),
    ]
    painter.drawPolygon(QPolygon(pts_base))
    painter.end()

    return pix.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def make_burger_pixmap(size=18, color=Theme.BRASS_LIGHT):
    """西洋アンティーク調のバーガーアイコン（三本線メニュー）を生成"""
    scale = 4
    S = size * scale
    pix = QPixmap(S, S)
    pix.fill(Qt.transparent)

    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(color))

    line_h = int(S * 0.12)
    line_w = int(S * 0.76)
    x = int((S - line_w) / 2)
    radius = int(line_h / 2)

    # 3本の丸みのある真鍮バー
    y1 = int(S * 0.22)
    y2 = int(S * 0.44)
    y3 = int(S * 0.66)

    painter.drawRoundedRect(x, y1, line_w, line_h, radius, radius)
    painter.drawRoundedRect(x, y2, line_w, line_h, radius, radius)
    painter.drawRoundedRect(x, y3, line_w, line_h, radius, radius)
    painter.end()

    return pix.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


class OrnateFrame(QFrame):
    """真鍮二重枠と四隅のクラシカルな金具ブラケットを描画する装飾フレーム"""
    def __init__(self, parent=None, bracket_size=18, bg_color=Theme.BG_PANEL, bg_pixmap=None, draw_border=True, fit_mode="stretch"):
        super().__init__(parent)
        self.bracket_size = bracket_size
        self.bg_color = bg_color
        self.bg_pixmap = bg_pixmap
        self.draw_border = draw_border
        self.fit_mode = fit_mode

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        w = self.width()
        h = self.height()

        # 背景画像、または背景色塗りつぶし
        if self.bg_pixmap and not self.bg_pixmap.isNull():
            if self.fit_mode == "stretch":
                painter.drawPixmap(0, 0, w, h, self.bg_pixmap)
            else:
                scaled = self.bg_pixmap.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                sx = (scaled.width() - w) // 2
                sy = (scaled.height() - h) // 2
                painter.drawPixmap(0, 0, scaled, sx, sy, w, h)
        else:
            if isinstance(self.bg_color, QColor):
                painter.fillRect(0, 0, w, h, self.bg_color)
            else:
                painter.fillRect(0, 0, w, h, QColor(self.bg_color))

        if not self.draw_border:
            painter.end()
            return

        # 外枠・内枠（二重真鍮ライン）
        c_base = QColor(Theme.BRASS_BASE)
        c_dark = QColor(Theme.BRASS_DARK)

        painter.setPen(QPen(c_base, 1))
        painter.drawRect(2, 2, w - 5, h - 5)

        painter.setPen(QPen(c_dark, 1))
        painter.drawRect(5, 5, w - 11, h - 11)

        # 四隅の真鍮ブラケット金具
        L = self.bracket_size
        painter.setPen(QPen(c_base, 2))

        # NW
        painter.drawLine(3, 3 + L, 3, 3)
        painter.drawLine(3, 3, 3 + L, 3)
        painter.setBrush(QBrush(c_base))
        painter.drawEllipse(1, 1, 5, 5)

        # NE
        painter.drawLine(w - 4 - L, 3, w - 4, 3)
        painter.drawLine(w - 4, 3, w - 4, 3 + L)
        painter.drawEllipse(w - 7, 1, 5, 5)

        # SW
        painter.drawLine(3, h - 4 - L, 3, h - 4)
        painter.drawLine(3, h - 4, 3 + L, h - 4)
        painter.drawEllipse(1, h - 7, 5, 5)

        # SE
        painter.drawLine(w - 4 - L, h - 4, w - 4, h - 4)
        painter.drawLine(w - 4, h - 4 - L, w - 4, h - 4)
        painter.drawEllipse(w - 7, h - 7, 5, 5)

        painter.end()


class OrnateDivider(QWidget):
    """中央にダイヤ飾り（◆）のある真鍮水平区切り線"""
    def __init__(self, parent=None, height=14, diamond_color=Theme.BRASS_LIGHT):
        super().__init__(parent)
        self.setFixedHeight(height)
        self.diamond_color = diamond_color

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        mid_y = self.height() // 2
        mid_x = w // 2

        # 水平線
        painter.setPen(QPen(QColor(Theme.BRASS_DARK), 1))
        painter.drawLine(6, mid_y, w - 6, mid_y)

        # 中央ダイヤ飾り
        d = 3
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(self.diamond_color)))
        pts = [
            QPoint(mid_x, mid_y - d),
            QPoint(mid_x + d, mid_y),
            QPoint(mid_x, mid_y + d),
            QPoint(mid_x - d, mid_y),
        ]
        painter.drawPolygon(QPolygon(pts))
        painter.end()


class PillTag(QFrame):
    """西洋アンティーク調のピル型タグ（しおり）ウィジェット"""
    toggled = Signal(str, bool)

    def __init__(self, text, color=None, is_checkable=True, parent=None):
        super().__init__(parent)
        self.text = text
        self.tag_color = color or Theme.BOOKMARK_COLORS.get(text, Theme.BRASS_DARK)
        self.is_checkable = is_checkable
        self.is_checked = False

        self.setCursor(Qt.PointingHandCursor if is_checkable else Qt.ArrowCursor)
        self.setFixedHeight(24)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)

        # 小さなカラーインジケータ丸
        self.dot = QLabel()
        self.dot.setFixedSize(8, 8)
        self.dot.setStyleSheet(f"background-color: {self.tag_color}; border-radius: 4px;")
        layout.addWidget(self.dot)

        # ラベル
        self.label = QLabel(text)
        self.label.setStyleSheet(f"color: {Theme.TEXT_WHITE}; font-size: 11px; background: transparent;")
        layout.addWidget(self.label)

        self._update_style()

    def _update_style(self):
        if self.is_checked:
            border = Theme.BRASS_LIGHT
            bg = "#34281c"
            text_color = Theme.BRASS_LIGHT
        else:
            border = Theme.BRASS_DARK
            bg = "#1c1713"
            text_color = Theme.TEXT_WHITE

        self.setStyleSheet(f"""
            PillTag {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 12px;
            }}
            PillTag:hover {{
                border: 1px solid {Theme.BRASS_BASE};
                background-color: #261f18;
            }}
        """)
        self.label.setStyleSheet(f"color: {text_color}; font-size: 11px; background: transparent;")

    def mousePressEvent(self, event):
        if self.is_checkable and event.button() == Qt.LeftButton:
            self.is_checked = not self.is_checked
            self._update_style()
            self.toggled.emit(self.text, self.is_checked)
        super().mousePressEvent(event)


class FlowLayout(QLayout):
    """横幅に応じて折り返すフローレイアウト（横に並べ、はみ出る場合は次行へ）"""
    def __init__(self, parent=None, margin=0, h_spacing=12, v_spacing=6):
        super().__init__(parent)
        self.setContentsMargins(margin, margin, margin, margin)
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing
        self._items = []

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), apply_geometry=False)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, apply_geometry=True)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect, apply_geometry=True):
        margins = self.contentsMargins()
        effective_rect = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x = effective_rect.x()
        y = effective_rect.y()
        line_height = 0

        for item in self._items:
            w = item.widget()
            if w and not w.isVisible():
                continue
            item_size = item.sizeHint()
            next_x = x + item_size.width() + self._h_spacing
            if next_x - self._h_spacing > effective_rect.right() and line_height > 0:
                x = effective_rect.x()
                y = y + line_height + self._v_spacing
                next_x = x + item_size.width() + self._h_spacing
                line_height = 0

            if apply_geometry:
                item.setGeometry(QRect(QPoint(x, y), item_size))

            x = next_x
            line_height = max(line_height, item_size.height())

        return y + line_height - rect.y() + margins.bottom()
