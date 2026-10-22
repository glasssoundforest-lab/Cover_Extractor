"""書架のカード下部に載せる、システム・人数のピルアイコン"""

import re
import unicodedata

from PySide6.QtCore import Qt, QSize, QRectF
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QWidget

from core.database import GLOBAL_TAG_COLORS, _is_murder_mystery, _is_story_playing

# 人数ごとの色（1 人 ... 5 人以上）。人数が読み取れないときは灰色
PLAYERS_COLORS = {
    1: "#b45f06",
    2: "#2e7d5b",
    3: "#1f6aa5",
    4: "#7b4fa3",
    5: "#a32f3d",
}
PLAYERS_UNKNOWN_COLOR = "#5f6b73"


def system_pill_info(system_text):
    """システム名から (ピルの文字, 色) を返す。CoC・マダミス・ストプレ・その他の 4 区分（色はグローバルタグと同じ）"""
    raw = unicodedata.normalize("NFKC", system_text or "").lower()
    if _is_murder_mystery(system_text):
        label = "マダミス"
    elif _is_story_playing(system_text):
        label = "ストプレ"
    elif "クトゥルフ" in raw or re.search(r"\bcoc\b|call of cthulhu|coc\d", raw):
        label = "CoC"
    else:
        label = "その他"
    return label, GLOBAL_TAG_COLORS[label]


def players_count(players_text):
    """人数の文字から、色分けに使う人数（範囲は多い方。5 人以上は 5）を返す。読み取れなければ None"""
    norm = unicodedata.normalize("NFKC", players_text or "")
    nums = [int(n) for n in re.findall(r"\d+", norm)]
    if not nums:
        if any(k in norm.lower() for k in ("ソロ", "タイマン", "一人", "gmレス", "kpレス")):
            return 1
        return None
    count = max(nums[:2]) if len(nums) >= 2 and re.search(r"[〜~\-ー]", norm) else nums[0]
    return min(max(count, 1), 5)


def players_pill_info(players_text):
    """人数から (ピルの文字, 色) を返す。人数が空なら None"""
    text = (players_text or "").strip()
    if not text:
        return None
    label = text if ("人" in text or "PL" in text.upper()) else f"{text}人"
    count = players_count(text)
    return label, PLAYERS_COLORS.get(count, PLAYERS_UNKNOWN_COLOR)


GM_LESS_COLOR = "#8a6d3b"
_DEFAULT_TAG_COLOR = "#546e7a"  # 色を決めていないローカルタグの既定色
_PLAYER_TAG = re.compile(r"^(\d+)(?:\s*[〜~\-]\s*(\d+))?\s*(?:pl|人|名)(?:以上)?$")


def player_tag_color(tag_name):
    """人数タグ（1PL・2〜4PL・5PL以上・GMレス）の色。人数タグでなければ None"""
    name = unicodedata.normalize("NFKC", tag_name or "").strip().lower()
    if name in ("gmレス", "kpレス"):
        return GM_LESS_COLOR
    m = _PLAYER_TAG.match(name)
    if not m:
        return None
    count = int(m.group(2) or m.group(1))
    return PLAYERS_COLORS[min(max(count, 1), 5)]


def resolve_tag_color(tag_name, color):
    """人数タグで、色が未設定（既定色）なら人数の色にする。ユーザーが選んだ色はそのまま使う"""
    if not color or str(color).lower() == _DEFAULT_TAG_COLOR:
        return player_tag_color(tag_name) or color
    return color


class CardPill(QWidget):
    """色つきの角丸ピル。スタイルシートを使わず自前で描くので、カードを多数並べても軽い"""

    def __init__(self, text, color, font_px=10, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._text = text
        self._color = QColor(color)
        self._font = QFont()
        self._font.setPixelSize(font_px)
        self._font.setBold(True)
        self._pad_x = max(7, font_px - 1)
        metrics = QFontMetrics(self._font)
        self._size = QSize(metrics.horizontalAdvance(text) + self._pad_x * 2, font_px + 10)
        self.setFixedSize(self._size)

    def text(self):
        return self._text

    def color(self):
        return self._color

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        radius = rect.height() / 2
        p.setPen(QPen(self._color.lighter(150), 1))
        p.setBrush(self._color)
        p.drawRoundedRect(rect, radius, radius)
        p.setPen(QColor("#ffffff"))
        p.setFont(self._font)
        p.drawText(rect, Qt.AlignCenter, self._text)
        p.end()
