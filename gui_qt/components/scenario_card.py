"""シナリオカード・リストカードウィジェット (gui_qt/components/scenario_card.py)

西洋古書・グリモワール調の書棚カード。
大・中・小のグリッド表示、および2カラム一覧（リスト）表示に対応します。
"""

from PySide6.QtCore import Qt, QByteArray, QBuffer, QIODevice, Signal, QPoint, QPropertyAnimation, QEasingCurve, QRectF
from PySide6.QtGui import QImage, QPixmap, QPainter, QColor, QPen, QBrush, QPainterPath
from PySide6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QWidget,
    QSizePolicy,
    QGraphicsDropShadowEffect,
)

from ..theme import Theme
from core.database import global_tag_sort_key
from .ornate import make_fleur_pixmap, PillTag


# -----------------------------------------------------------------------------
# 表紙画像の加工（QImage のみを使うため、画面スレッド以外からも呼べる）
# -----------------------------------------------------------------------------
LIST_THUMB_SIZE = 91


def _read_image(data):
    """表紙データを QImage として読み込む（読めなければ空の QImage）"""
    img = QImage()
    img.loadFromData(QByteArray(bytes(data)))
    return img


def analyze_overlay_color(image, tw, th, overlay_h):
    """文字描画領域（下部 overlay_h）の表紙画像の平均色彩・輝度を高速サンプリング（QImage / QPixmap 両対応）"""
    if image is None or image.isNull():
        return None
    crop_y = max(0, th - overlay_h)
    region = image.copy(0, crop_y, tw, overlay_h)
    if region.isNull():
        return None
    if isinstance(region, QPixmap):
        region = region.toImage()
    # 16x8 に縮小して平均RGB・輝度・色相を算出
    img = region.scaled(16, 8, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    w, h = img.width(), img.height()
    if w == 0 or h == 0:
        return None
    total_r = total_g = total_b = 0
    num = w * h
    for y in range(h):
        for x in range(w):
            c = img.pixelColor(x, y)
            total_r += c.red()
            total_g += c.green()
            total_b += c.blue()
    avg_r = total_r / num
    avg_g = total_g / num
    avg_b = total_b / num
    lum = 0.299 * avg_r + 0.587 * avg_g + 0.114 * avg_b
    qcol = QColor(int(avg_r), int(avg_g), int(avg_b))
    return {
        "r": avg_r, "g": avg_g, "b": avg_b,
        "lum": lum, "hue": qcol.hue(), "sat": qcol.saturation(), "val": qcol.value()
    }


def check_color_conflict(color_info):
    """文字描画部分が文字基本色（真鍮ゴールド #d4b26f）と同系色または埋もれる色かどうかを判定"""
    if not color_info:
        return False
    lum = color_info["lum"]
    hue = color_info["hue"]
    r = color_info["r"]
    g = color_info["g"]
    b = color_info["b"]

    # 1. 真鍮ゴールドと同系色相（黄・金・橙・キャメル・黄土色）
    # Hue 18〜70度で、ある程度明るい場合
    is_gold_family = (18 <= hue <= 70) and (lum > 65)

    # 2. 真鍮ゴールド (#d4b26f: RGB 212, 178, 111) とのユークリッド色差が近い
    dist_to_gold = ((r - 212) ** 2 + (g - 178) ** 2 + (b - 111) ** 2) ** 0.5
    is_close_to_gold = dist_to_gold < 115

    # 3. 高明度（白、淡色、明るいパステルトーン）でゴールドが同化する
    is_high_luminance = lum > 130

    # 4. 明るい暖色（赤みの強い黄色、サンドベージュ）
    is_warm_light = (r > 150 and g > 125 and b < 145)

    return is_gold_family or is_close_to_gold or is_high_luminance or is_warm_light


def _card_thumb_config(size_mode):
    cfg = ScenarioCard.SIZE_CONFIGS.get(size_mode, ScenarioCard.SIZE_CONFIGS["medium"])
    return cfg["thumb"], cfg.get("overlay_h", 82)


def crop_card_cover(data, size_mode):
    """グリッド用カードの表紙を枠の大きさに縮小・中央切り抜きする（角丸加工前）。
    (QImage, 文字色の同系色衝突) を返す。読めなければ (None, False)。"""
    (tw, th), overlay_h = _card_thumb_config(size_mode)
    img = _read_image(data)
    if img.isNull():
        return None, False
    scaled = img.scaled(tw, th, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    sx = max(0, (scaled.width() - tw) // 2)
    sy = max(0, (scaled.height() - th) // 2)
    cropped = scaled.copy(sx, sy, tw, th)

    # 文字描画領域の色彩を解析し、同系色衝突がないか判定
    conflict = check_color_conflict(analyze_overlay_color(cropped, tw, th, overlay_h))
    return cropped, conflict


def round_card_cover(cropped, size_mode):
    """切り抜き済みの表紙をカードの角丸に合わせてクリッピングする"""
    (tw, th), _overlay_h = _card_thumb_config(size_mode)
    target = QImage(tw, th, QImage.Format_ARGB32_Premultiplied)
    target.fill(Qt.transparent)
    p = QPainter(target)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    path = QPainterPath()
    path.addRoundedRect(0, 0, tw, th, 4, 4)
    p.setClipPath(path)
    p.drawImage(0, 0, cropped)
    p.end()
    return target


def render_card_cover(data, size_mode):
    """グリッド用カードの表紙を作る。(角丸クリップ済み QImage, 文字色の同系色衝突) を返す。読めなければ (None, False)。"""
    cropped, conflict = crop_card_cover(data, size_mode)
    if cropped is None:
        return None, False
    return round_card_cover(cropped, size_mode), conflict


def render_list_cover(data):
    """一覧表示用カードの表紙（縦横比を保って 91px に収める）を作る。読めなければ None。"""
    img = _read_image(data)
    if img.isNull():
        return None
    return img.scaled(LIST_THUMB_SIZE, LIST_THUMB_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def render_cover(data, size_mode):
    """size_mode に応じた表紙を作る。(QImage または None, 同系色衝突) を返す。"""
    base, conflict = render_cover_base(data, size_mode)
    return finish_cover(base, size_mode), conflict


# 表紙キャッシュ（DB の cover_cache）には、手間のかかる「元画像の読み込み・縮小・切り抜き」までを済ませた画像を保存し、
# 角丸加工は読み出し時に行う。加工方法を変えたら COVER_CACHE_VERSION を上げると、古いキャッシュは使われなくなる。
COVER_CACHE_VERSION = 1


def render_cover_base(data, size_mode):
    """キャッシュに保存する段階までの表紙を作る。(QImage または None, 同系色衝突) を返す。"""
    if size_mode == "list":
        return render_list_cover(data), False
    return crop_card_cover(data, size_mode)


def finish_cover(base, size_mode):
    """render_cover_base（またはキャッシュから読んだ画像）を表示用に仕上げる"""
    if base is None or base.isNull():
        return None
    if size_mode == "list":
        return base
    return round_card_cover(base, size_mode)


def encode_cover(image):
    """キャッシュ保存用に表紙画像を PNG（劣化なし。直接加工した場合と同じ見た目になる）へ変換する。失敗時は None。"""
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    # 圧縮は軽めにする（最大圧縮は大きさがほぼ変わらないのに数倍遅い）
    ok = image.save(buf, "PNG", 80)
    buf.close()
    return bytes(ba) if ok else None


def decode_cover(data):
    """encode_cover で保存した画像を読み込む。読めなければ None。"""
    img = _read_image(data)
    return None if img.isNull() else img


def _is_image_data(value):
    return isinstance(value, (bytes, bytearray, memoryview)) and len(value) > 0


_placeholder_cache = {}


def _card_placeholder(size_mode, tw, th, overlay_h):
    """表紙がないカードのプレースホルダー（枠全体にダークレザー調の背景＋中央の百合の紋章）。サイズごとに1度だけ描く。"""
    key = ("card", size_mode)
    if key not in _placeholder_cache:
        placeholder = QPixmap(tw, th)
        placeholder.fill(Qt.transparent)
        p = QPainter(placeholder)
        p.setRenderHint(QPainter.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(0, 0, tw, th, 4, 4)
        p.fillPath(path, QColor("#16120f"))

        fleur = make_fleur_pixmap(28 if size_mode == "small" else 38, Theme.BRASS_BASE)
        fx = (tw - fleur.width()) // 2
        avail_h = th - overlay_h
        fy = (avail_h - fleur.height()) // 2
        p.drawPixmap(fx, fy, fleur)

        p.setPen(QPen(QColor(Theme.BRASS_DARK), 1))
        p.drawLine(28, fy + fleur.height() + 12, tw - 28, fy + fleur.height() + 12)
        p.end()
        _placeholder_cache[key] = placeholder
    return _placeholder_cache[key]


def _list_placeholder():
    key = ("list",)
    if key not in _placeholder_cache:
        size = LIST_THUMB_SIZE
        placeholder = QPixmap(size, size)
        placeholder.fill(QColor("#16120f"))
        p = QPainter(placeholder)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(Theme.BRASS_DARK), 1))
        p.drawRect(2, 2, 86, 86)
        fleur = make_fleur_pixmap(20, Theme.BRASS_BASE)
        p.drawPixmap((size - fleur.width()) // 2, (size - fleur.height()) // 2, fleur)
        p.end()
        _placeholder_cache[key] = placeholder
    return _placeholder_cache[key]


class CardBorderOverlay(QWidget):
    """カード最前面に重ね、四辺（上下左右）すべてを均等・美麗に囲む枠線専用オーバーレイ"""
    def __init__(self, parent=None, radius=4):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.border_color = QColor(Theme.BRASS_BASE)
        self.border_width = 1.5
        self.radius = radius

    def set_border(self, color, width=1.5):
        self.border_color = QColor(color)
        self.border_width = width
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(self.border_color, self.border_width)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        half = self.border_width / 2.0
        w = float(self.width())
        h = float(self.height())
        rf = QRectF(half, half, max(0.0, w - self.border_width), max(0.0, h - self.border_width))
        p.drawRoundedRect(rf, self.radius, self.radius)
        p.end()


class ScenarioSlideOverlay(QFrame):
    """カードホバー時に下からスライドインする概要・あらすじオーバーレイパネル"""
    def __init__(self, parent, target_width, target_height, overview="", synopsis="", size_mode="medium"):
        super().__init__(parent)
        self.target_width = target_width
        self.target_height = target_height
        self.size_mode = size_mode

        # クリック等のマウスイベントを下のカードに透過
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_StyledBackground, True)

        # パネルの高さ決定
        if size_mode == "large":
            self.overlay_height = int(target_height * 0.82)
            title_font_size = 12
            body_font_size = 11
        elif size_mode == "small":
            self.overlay_height = int(target_height * 0.86)
            title_font_size = 10
            body_font_size = 9
        elif size_mode == "list":
            self.overlay_height = int(target_height * 0.85)
            title_font_size = 9
            body_font_size = 8
        else:  # medium
            self.overlay_height = int(target_height * 0.84)
            title_font_size = 11
            body_font_size = 10

        self.setFixedSize(self.target_width, self.overlay_height)

        # 初期位置（親枠の真下、完全に隠れた状態）
        self.hide_y = target_height
        self.show_y = target_height - self.overlay_height
        self.move(0, self.hide_y)
        self.hide()

        # スライドアニメーション（速度を少し落とし滑らかにする）
        self.anim = QPropertyAnimation(self, b"pos")
        self.anim.setDuration(360)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.finished.connect(self._on_anim_finished)

        # 内部レイアウト
        layout = QVBoxLayout(self)
        pad_lr = 6 if size_mode in ("small", "list") else 8
        pad_tb = 4 if size_mode in ("small", "list") else 6
        layout.setContentsMargins(pad_lr, pad_tb, pad_lr, pad_tb)
        layout.setSpacing(3)

        syn = (synopsis or "").strip()
        ovr = (overview or "").strip()
        if syn:
            header_text = "📜 あらすじ"
            display_text = syn
        elif ovr:
            header_text = "📜 概要"
            display_text = ovr
        else:
            header_text = "📜 あらすじ・概要"
            display_text = "あらすじ・概要は未登録です\n（ダブルクリックで編集）"

        self.title_lbl = QLabel(header_text)
        self.title_lbl.setStyleSheet(f"""
            color: {Theme.BRASS_LIGHT};
            font-size: {title_font_size}px;
            font-weight: bold;
            font-family: {Theme.FONT_SERIF};
            background: transparent;
        """)
        layout.addWidget(self.title_lbl)

        self.body_lbl = QLabel(display_text)
        self.body_lbl.setWordWrap(True)
        self.body_lbl.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.body_lbl.setTextFormat(Qt.PlainText)
        self.body_lbl.setStyleSheet(f"""
            color: {Theme.TEXT_WHITE};
            font-size: {body_font_size}px;
            line-height: 1.35;
            background: transparent;
        """)
        layout.addWidget(self.body_lbl, 1)

        # アンティーク調半透明ダーク背景・上部真鍮光沢ボーダー
        self.setStyleSheet(f"""
            ScenarioSlideOverlay {{
                background-color: rgba(18, 14, 11, 0.94);
                border-top: 1px solid {Theme.BRASS_LIGHT};
                border-bottom-left-radius: 2px;
                border-bottom-right-radius: 2px;
            }}
        """)

    def slide_in(self):
        """下から上へスライドイン"""
        self.anim.stop()
        self.show()
        self.raise_()
        self.anim.setStartValue(self.pos())
        self.anim.setEndValue(QPoint(0, self.show_y))
        self.anim.start()

    def slide_out(self):
        """上から下へスライドアウト"""
        self.anim.stop()
        self.anim.setStartValue(self.pos())
        self.anim.setEndValue(QPoint(0, self.hide_y))
        self.anim.start()

    def _on_anim_finished(self):
        if self.y() >= self.hide_y:
            self.hide()


class BookmarkRibbon(QWidget):
    """西洋古書調のしおりリボン（表紙右上に垂れ下がるタグ同色のシルクリボン）"""
    def __init__(self, color_hex, tag_name="", width=14, height=28, parent=None):
        super().__init__(parent)
        self.color_hex = color_hex or "#546e7a"
        self.color = QColor(self.color_hex)
        self.tag_name = tag_name
        self.setFixedSize(width, height)
        if tag_name:
            self.setToolTip(f"しおり: {tag_name}")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        cut = int(w * 0.42)  # 下部のV字切れ込み深さ

        # リボンのパス（上辺・左右辺・下部V字切れ込み）
        path = QPainterPath()
        path.moveTo(0, 0)
        path.lineTo(w, 0)
        path.lineTo(w, h)
        path.lineTo(w / 2, h - cut)
        path.lineTo(0, h)
        path.closeSubpath()

        # 1. 背面のドロップシャドウ
        p.save()
        p.translate(1, 1)
        p.fillPath(path, QColor(0, 0, 0, 80))
        p.restore()

        # 2. リボン本体塗りつぶし
        p.fillPath(path, self.color)

        # 3. 光沢ハイライト（左寄りにうっすら光の反射）
        highlight_color = QColor(255, 255, 255, 55)
        p.setPen(QPen(highlight_color, 1))
        p.drawLine(2, 2, 2, h - cut - 2)

        # 4. 外枠（アンティーク真鍮の細線）
        p.setPen(QPen(QColor(Theme.BRASS_LIGHT), 1))
        p.drawPath(path)

        # 5. 上端の真鍮留め具バー
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(Theme.BRASS_LIGHT)))
        p.drawRect(0, 0, w, 2)

        p.end()

    def mousePressEvent(self, event):
        event.ignore()


# -----------------------------------------------------------------------------
# カードの見た目（スタイルシート）
#
# カードごとに setStyleSheet を何度も呼ぶと、そのたびにスタイルの解析とやり直しが起き、
# カードの生成・ホバーが重くなる。見た目の規則はここで1度だけ定義し、書架（親ウィジェット）に設定する。
# カードの状態（ホバー・選択中 = active、文字色の同系色衝突 = conflict、大きさ = cardSize）は
# 動的プロパティで切り替える。
# -----------------------------------------------------------------------------
_OVERLAY_GRADIENTS = {
    # (conflict, active): 下部オーバーレイのグラデーション
    (False, False): "stop: 0.0 rgba(10, 7, 5, 0.0), stop: 0.25 rgba(10, 7, 5, 0.35), stop: 0.60 rgba(10, 7, 5, 0.75), stop: 1.0 rgba(10, 7, 5, 0.90)",
    (False, True): "stop: 0.0 rgba(14, 10, 7, 0.0), stop: 0.25 rgba(14, 10, 7, 0.40), stop: 0.60 rgba(14, 10, 7, 0.82), stop: 1.0 rgba(12, 8, 5, 0.96)",
    # 同系色の黄色・明色背景をしっかり引き締めるシャドウグラデーション
    (True, False): "stop: 0.0 rgba(10, 7, 5, 0.22), stop: 0.25 rgba(10, 7, 5, 0.50), stop: 0.60 rgba(10, 7, 5, 0.85), stop: 1.0 rgba(10, 7, 5, 0.96)",
    (True, True): "stop: 0.0 rgba(14, 10, 7, 0.30), stop: 0.25 rgba(14, 10, 7, 0.60), stop: 0.60 rgba(14, 10, 7, 0.90), stop: 1.0 rgba(12, 8, 5, 0.98)",
}

# (conflict, active): (書名の色, 概要情報の色)
_CARD_TEXT_COLORS = {
    (False, False): (Theme.BRASS_LIGHT, "#e2c07d"),
    (False, True): (Theme.BRASS_LIGHT, "#f4ecdf"),
    (True, False): ("#ffffff", "#f1f5f9"),
    (True, True): ("#ffffff", "#ffffff"),
}


def _bool_prop(value):
    return "true" if value else "false"


def _build_card_stylesheet():
    rules = [f"""
        ScenarioCard {{
            background-color: {Theme.BG_CARD};
            border: 1.5px solid {Theme.BRASS_BASE};
            border-radius: 4px;
        }}
        ScenarioCard[active="true"] {{
            background-color: {Theme.BG_CARD_HOVER};
            border: 1.5px solid {Theme.BRASS_LIGHT};
        }}
        ScenarioCard QFrame#thumbContainer {{
            background-color: transparent;
            border: none;
            border-radius: 4px;
        }}
        ScenarioCard QLabel#thumbImage {{
            background: transparent;
            border: none;
        }}
        ScenarioCard QLabel#favBadge, ScenarioListCard QLabel#favBadge {{
            background-color: rgba(22, 14, 10, 0.88);
            color: #f1c40f;
            border: 1px solid {Theme.BRASS_LIGHT};
            border-radius: 3px;
            font-size: 12px;
            font-weight: bold;
            padding-bottom: 1px;
        }}
        ScenarioCard QLabel#bookmarkBadge, ScenarioListCard QLabel#bookmarkBadge {{
            background-color: rgba(22, 14, 10, 0.88);
            color: #e2c07d;
            border: 1px solid {Theme.BRASS_LIGHT};
            border-radius: 3px;
            font-size: 11px;
            padding-bottom: 1px;
        }}
        ScenarioCard[cardSize="small"] QLabel#favBadge, ScenarioListCard QLabel#favBadge {{ font-size: 10px; }}
        ScenarioCard[cardSize="small"] QLabel#bookmarkBadge, ScenarioListCard QLabel#bookmarkBadge {{ font-size: 9px; }}
    """]
    for (conflict, active), stops in _OVERLAY_GRADIENTS.items():
        title_color, meta_color = _CARD_TEXT_COLORS[(conflict, active)]
        sel = f'ScenarioCard[conflict="{_bool_prop(conflict)}"][active="{_bool_prop(active)}"]'
        rules.append(f"""
        {sel} QFrame#cardOverlay {{
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, {stops});
            border: none;
            border-bottom-left-radius: 4px;
            border-bottom-right-radius: 4px;
        }}
        {sel} QLabel#cardTitle {{ color: {title_color}; font-weight: bold; background: transparent; border: none; }}
        {sel} QLabel#cardMeta {{ color: {meta_color}; background: transparent; border: none; }}
        """)
    for size, cfg in ScenarioCard.SIZE_CONFIGS.items():
        rules.append(f"""
        ScenarioCard[cardSize="{size}"] QLabel#cardTitle {{ font-size: {cfg["font_title"]}px; }}
        ScenarioCard[cardSize="{size}"] QLabel#cardMeta {{ font-size: {cfg["font_sub"]}px; }}
        """)
    rules.append(f"""
        ScenarioListCard {{
            background-color: {Theme.BG_CARD};
            border: 1px solid {Theme.BRASS_BASE};
            border-radius: 3px;
        }}
        ScenarioListCard[active="true"] {{
            background-color: {Theme.BG_CARD_HOVER};
            border: 1px solid {Theme.BRASS_LIGHT};
        }}
        ScenarioListCard QFrame#listThumb {{
            background-color: #120e0c;
            border: 1.5px solid {Theme.BRASS_DARK};
            border-radius: 2px;
        }}
        ScenarioListCard[active="true"] QFrame#listThumb {{ border: 1.5px solid {Theme.BRASS_LIGHT}; }}
        ScenarioListCard QLabel#thumbImage {{ background: transparent; border: none; }}
        ScenarioListCard QLabel#listTitle {{ color: {Theme.TEXT_WHITE}; font-weight: bold; font-size: 13px; background: transparent; }}
        ScenarioListCard[active="true"] QLabel#listTitle {{ color: {Theme.BRASS_LIGHT}; }}
        ScenarioListCard QLabel#listSystem {{ color: {Theme.TEXT_MUTED}; font-size: 11px; background: transparent; }}
        ScenarioListCard[active="true"] QLabel#listSystem {{ color: {Theme.BRASS_LIGHT}; }}
        ScenarioListCard QLabel#listMeta {{ color: {Theme.TEXT_MUTED}; font-size: 10px; background: transparent; }}
        ScenarioListCard QLabel#listOverview {{ color: #7a6e60; font-size: 10px; background: transparent; }}
    """)
    return "\n".join(rules)


_card_stylesheet = None


def card_stylesheet():
    """カードの見た目の規則（書架などカードを並べる親ウィジェットに1度だけ設定する）"""
    global _card_stylesheet
    if _card_stylesheet is None:
        _card_stylesheet = _build_card_stylesheet()
    return _card_stylesheet


def _repolish(*widgets):
    for w in widgets:
        style = w.style()
        style.unpolish(w)
        style.polish(w)


class _StyledCardMixin:
    """親に card_stylesheet() が設定されていない場所で表示された場合だけ、カード自身に設定する"""

    def _ensure_card_style(self):
        if getattr(self, "_style_checked", False):
            return
        self._style_checked = True
        w = self.parentWidget()
        while w is not None:
            if w.property("cardStyleHost"):
                return
            w = w.parentWidget()
        self.setStyleSheet(card_stylesheet())

    def showEvent(self, event):
        self._ensure_card_style()
        super().showEvent(event)


def _make_badge(text, object_name, size, parent):
    badge = QLabel(text, parent)
    badge.setObjectName(object_name)
    badge.setAlignment(Qt.AlignCenter)
    badge.setFixedSize(size, size)
    return badge


def _ribbon_entries(global_tags):
    """グローバルタグを優先順序（CoC > マダミス > 未通過 > 通過済 > GM可）で (名前, 色) にする"""
    entries = []
    for tag_item in sorted(global_tags, key=global_tag_sort_key):
        if isinstance(tag_item, (list, tuple)):
            if len(tag_item) >= 3:
                entries.append((tag_item[1], tag_item[2]))
            else:
                entries.append((tag_item[0], tag_item[1] if len(tag_item) > 1 else None))
        else:
            entries.append((str(tag_item), None))
    return entries


class ScenarioCard(_StyledCardMixin, QFrame):
    """グリッド表示用シナリオカード（大・中・小）"""
    clicked = Signal(int)
    double_clicked = Signal(int)
    context_menu_requested = Signal(int, QPoint)
    hover_entered = Signal(object) # item
    hover_left = Signal(object)    # item

    SIZE_CONFIGS = {
        "large": {"card": (270, 380), "thumb": (270, 380), "overlay_h": 96, "font_title": 13, "font_sub": 10},
        "medium": {"card": (216, 305), "thumb": (216, 305), "overlay_h": 82, "font_title": 12, "font_sub": 9},
        "small": {"card": (165, 235), "thumb": (165, 235), "overlay_h": 68, "font_title": 11, "font_sub": 8},
    }

    @staticmethod
    def _round_pixmap(pixmap, w, h, radius=4):
        """カードの角丸に合わせて Pixmap を美しくクリッピング"""
        target = QPixmap(w, h)
        target.fill(Qt.transparent)
        p = QPainter(target)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        path = QPainterPath()
        path.addRoundedRect(0, 0, w, h, radius, radius)
        p.setClipPath(path)
        p.drawPixmap(0, 0, w, h, pixmap)
        p.end()
        return target

    def __init__(self, item, size_mode="medium", tags=None, global_tags=None, parent=None):
        super().__init__(parent)
        self.item = item
        self.item_id = item[0]
        self.size_mode = size_mode if size_mode in self.SIZE_CONFIGS else "medium"
        self.cfg = self.SIZE_CONFIGS[self.size_mode]

        self.title_text = item[2] or "無題"
        self.system_text = item[3] or "システム未設定"
        self.players_text = item[4] or ""
        self.duration_text = item[5] or ""
        self.overview_text = (item[6] or "").strip() if len(item) > 6 and item[6] else ""
        self.synopsis_text = (item[7] or "").strip() if len(item) > 7 and item[7] else ""
        self.thumb_bytes = item[8]
        # 表紙のバイト列ではなく表紙のサイズ（int）が渡された場合は、書架が後から表紙を届ける
        self.thumb_key = None if _is_image_data(item[8]) else item[8]
        self.cover_loaded = False
        self.is_favorite = bool(item[9]) if len(item) > 9 and item[9] is not None else False
        self.is_bookmarked = bool(item[10]) if len(item) > 10 and item[10] is not None else False
        self.tags = tags or []
        self.global_tags = global_tags or []
        self.bookmark_ribbons = []

        self.is_hovered = False
        self.is_selected = False
        self.has_color_conflict = False
        self._applied_state = None

        self.setProperty("cardSize", self.size_mode)
        cw, ch = self.cfg["card"]
        self.setFixedSize(cw, ch)
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 1. 表紙サムネイル領域（カード枠の上下左右いっぱいに敷き詰める）
        tw, th = self.cfg["thumb"]
        self.thumb_container = QFrame(self)
        self.thumb_container.setObjectName("thumbContainer")
        self.thumb_container.setFixedSize(tw, th)
        self.thumb_layout = QVBoxLayout(self.thumb_container)
        self.thumb_layout.setContentsMargins(0, 0, 0, 0)

        self.thumb_label = QLabel()
        self.thumb_label.setObjectName("thumbImage")
        self.thumb_label.setAlignment(Qt.AlignCenter)
        self.thumb_layout.addWidget(self.thumb_label)

        # 表紙左上のお気に入りシンボル（アンティーク星バッジ）・しおりシンボル（アンティーク栞バッジ）
        badge_size = 18 if self.size_mode == "small" else 22
        self.fav_badge = _make_badge("★", "favBadge", badge_size, self.thumb_container)
        self.bookmark_badge = _make_badge("🔖", "bookmarkBadge", badge_size, self.thumb_container)
        self._update_badges()

        # 表紙の上に重ねるフェードオーバーレイ（上部完全透明グラデーション・仕切り線なし）
        overlay_h = self.cfg.get("overlay_h", 82)
        self.thumb_overlay = QFrame(self.thumb_container)
        self.thumb_overlay.setObjectName("cardOverlay")
        self.thumb_overlay.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.thumb_overlay.setFixedSize(tw, overlay_h)
        self.thumb_overlay.move(0, th - overlay_h)

        overlay_layout = QVBoxLayout(self.thumb_overlay)
        overlay_layout.setContentsMargins(9, 6, 9, 8)
        overlay_layout.setSpacing(3)

        # 書名（真鍮金文字／同系色時は白文字＋ドロップシャドウで視認性担保）
        self.title_label = QLabel(self.title_text)
        self.title_label.setObjectName("cardTitle")
        self.title_label.setTextFormat(Qt.PlainText)
        self.title_label.setWordWrap(True)
        self.title_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.title_shadow = QGraphicsDropShadowEffect(self.title_label)
        self.title_shadow.setOffset(1, 1)
        self.title_label.setGraphicsEffect(self.title_shadow)
        overlay_layout.addWidget(self.title_label)

        # 概要情報（システム名 │ 人数 │ 時間 ＋ ドロップシャドウ）
        meta_parts = [self.system_text]
        if self.players_text:
            pt = self.players_text if ("人" in self.players_text or "PL" in self.players_text) else f"{self.players_text}人"
            meta_parts.append(pt)
        if self.duration_text:
            meta_parts.append(self.duration_text)
        meta_text = " │ ".join(meta_parts)

        self.meta_label = QLabel(meta_text)
        self.meta_label.setObjectName("cardMeta")
        self.meta_label.setTextFormat(Qt.PlainText)
        self.meta_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.meta_shadow = QGraphicsDropShadowEffect(self.meta_label)
        self.meta_shadow.setOffset(1, 1)
        self.meta_label.setGraphicsEffect(self.meta_shadow)
        overlay_layout.addWidget(self.meta_label)

        # 互換用ダミー（テストや外部参照用）
        self.sys_label = QLabel(self.system_text)
        self.sys_label.hide()
        self._load_thumbnail(tw, th)
        self._setup_bookmarks()
        layout.addWidget(self.thumb_container)

        # 最前面ボーダーオーバーレイ（表紙画像の重なりで右・下辺が欠けるのを防ぎ、四辺すべてを美しく囲む）
        self.border_overlay = CardBorderOverlay(self, radius=4)
        self.border_overlay.setGeometry(0, 0, cw, ch)
        self.border_overlay.raise_()

        self._update_appearance()

    def _analyze_overlay_color(self, pixmap, tw, th, overlay_h):
        """文字描画領域（下部 overlay_h）の表紙画像の平均色彩・輝度を高速サンプリング"""
        return analyze_overlay_color(pixmap, tw, th, overlay_h)

    def _check_color_conflict(self, color_info):
        """文字描画部分が文字基本色（真鍮ゴールド #d4b26f）と同系色または埋もれる色かどうかを判定"""
        return check_color_conflict(color_info)

    def _load_thumbnail(self, tw, th):
        """表紙画像を枠の上下左右いっぱいに描画（隙間ゼロ・角丸クリップ）

        表紙のバイト列を渡された場合はここで描画する。書架から表紙のサイズ（int）だけを渡された場合は
        プレースホルダーを描き、書架のバックグラウンド読み込みから set_cover_image() で受け取る。
        """
        if _is_image_data(self.thumb_bytes):
            image, conflict = render_card_cover(self.thumb_bytes, self.size_mode)
            if image is not None:
                self.has_color_conflict = conflict
                self.cover_loaded = True
                self.thumb_label.setPixmap(QPixmap.fromImage(image))
                return

        self.has_color_conflict = False
        self.thumb_label.setPixmap(_card_placeholder(self.size_mode, tw, th, self.cfg.get("overlay_h", 82)))

    @property
    def needs_cover(self):
        """書架のバックグラウンド読み込みで表紙を届ける必要があるか"""
        return bool(self.thumb_key) and not self.cover_loaded

    def set_cover_image(self, image, conflict=False):
        """バックグラウンドで作った表紙（QImage）を反映する"""
        self.cover_loaded = True
        if image is None or image.isNull():
            return
        self.has_color_conflict = conflict
        self.thumb_label.setPixmap(QPixmap.fromImage(image))
        self._update_appearance()

    def title_color(self):
        """現在の書名の文字色（#rrggbb）"""
        return _CARD_TEXT_COLORS[(bool(self.has_color_conflict), self.is_hovered or self.is_selected)][0]

    def _update_appearance(self):
        active = bool(self.is_hovered or self.is_selected)
        conflict = bool(self.has_color_conflict)
        state = (active, conflict)
        if state == self._applied_state:
            return
        first = self._applied_state is None
        self._applied_state = state

        # 同系色・埋もれ対策: 背景が文字（ゴールド）と同系色または明るい場合は文字を純白にし、シャドウを強化
        if conflict:
            shadow_blur_t, shadow_blur_m, shadow_alpha = 5, 4, 245
        else:
            shadow_blur_t, shadow_blur_m, shadow_alpha = 4, 3, 225
        self.title_shadow.setBlurRadius(shadow_blur_t)
        self.title_shadow.setColor(QColor(0, 0, 0, shadow_alpha))
        self.meta_shadow.setBlurRadius(shadow_blur_m)
        self.meta_shadow.setColor(QColor(0, 0, 0, shadow_alpha - 10))

        self.setProperty("active", _bool_prop(active))
        self.setProperty("conflict", _bool_prop(conflict))
        if not first:
            # 状態に応じた規則を当て直す（初回は表示時にまとめて適用される）
            _repolish(self, self.thumb_overlay, self.title_label, self.meta_label)

        if active:
            self.border_overlay.set_border(Theme.BRASS_LIGHT, width=2.0)
        else:
            self.border_overlay.set_border(Theme.BRASS_BASE, width=1.5)
        self.border_overlay.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "border_overlay"):
            self.border_overlay.setGeometry(0, 0, self.width(), self.height())
            self.border_overlay.raise_()

    def set_selected(self, selected):
        self.is_selected = selected
        self._update_appearance()

    def _update_badges(self):
        badge_size = 18 if self.size_mode == "small" else 22
        self.fav_badge.setVisible(self.is_favorite)
        self.bookmark_badge.setVisible(self.is_bookmarked)

        cur_x = 5
        if self.is_favorite:
            self.fav_badge.move(cur_x, 5)
            cur_x += badge_size + 3
        if self.is_bookmarked:
            self.bookmark_badge.move(cur_x, 5)

    def set_favorite(self, is_fav):
        self.is_favorite = is_fav
        self._update_badges()

    def set_bookmarked(self, is_bm):
        self.is_bookmarked = is_bm
        self._update_badges()

    def set_global_tags(self, global_tags):
        self.global_tags = global_tags or []
        self._setup_bookmarks()

    def _setup_bookmarks(self):
        """表紙右上にグローバルタグと同色のしおりリボンを配置"""
        for rb in getattr(self, "bookmark_ribbons", []):
            rb.setParent(None)
            rb.deleteLater()
        self.bookmark_ribbons = []

        if not self.global_tags:
            return

        tw, _ = self.cfg["thumb"]
        if self.size_mode == "large":
            rw, rh = 16, 32
        elif self.size_mode == "small":
            rw, rh = 12, 22
        else:
            rw, rh = 14, 28

        right_margin = 6
        spacing = 3

        # 優先順序（CoC > マダミス > 未通過 > 通過済 > GM可）で右端から左へ順に並べる
        for i, (tname, tcolor) in enumerate(_ribbon_entries(self.global_tags)):
            x = tw - right_margin - (i + 1) * rw - i * spacing
            if x < 28:  # 左上のお気に入りバッジと干渉しないよう安全マージン
                break

            ribbon = BookmarkRibbon(tcolor, tag_name=tname, width=rw, height=rh, parent=self.thumb_container)
            ribbon.move(x, 0)
            ribbon.show()
            self.bookmark_ribbons.append(ribbon)

        if hasattr(self, "border_overlay"):
            self.border_overlay.raise_()

    def enterEvent(self, event):
        self.is_hovered = True
        self._update_appearance()
        self.hover_entered.emit(self.item)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.is_hovered = False
        self._update_appearance()
        self.hover_left.emit(self.item)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.item_id)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit(self.item_id)
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        self.context_menu_requested.emit(self.item_id, event.globalPos())


class ScenarioListCard(_StyledCardMixin, QFrame):
    """一覧（2カラムリスト）表示用シナリオ行カード"""
    clicked = Signal(int)
    double_clicked = Signal(int)
    context_menu_requested = Signal(int, QPoint)
    hover_entered = Signal(object) # item
    hover_left = Signal(object)    # item

    HEIGHT = 115

    def __init__(self, item, tags=None, global_tags=None, parent=None):
        super().__init__(parent)
        self.item = item
        self.item_id = item[0]
        self.title_text = item[2] or "無題"
        self.system_text = item[3] or "システム未設定"
        self.players_text = item[4] or ""
        self.duration_text = item[5] or ""
        self.overview_text = (item[6] or "").strip() if len(item) > 6 and item[6] else ""
        self.synopsis_text = (item[7] or "").strip() if len(item) > 7 and item[7] else ""
        self.thumb_bytes = item[8]
        # 表紙のバイト列ではなく表紙のサイズ（int）が渡された場合は、書架が後から表紙を届ける
        self.thumb_key = None if _is_image_data(item[8]) else item[8]
        self.cover_loaded = False
        self.is_favorite = bool(item[9]) if len(item) > 9 and item[9] is not None else False
        self.is_bookmarked = bool(item[10]) if len(item) > 10 and item[10] is not None else False
        self.tags = tags or []
        self.global_tags = global_tags or []
        self.bookmark_ribbons = []

        self.is_hovered = False
        self.is_selected = False
        self._applied_active = None

        self.setFixedHeight(self.HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 12, 8)
        layout.setSpacing(12)

        # 1. 左側サムネイル (95 x 95)
        self.thumb_frame = QFrame()
        self.thumb_frame.setObjectName("listThumb")
        self.thumb_frame.setFixedSize(95, 95)
        tf_layout = QVBoxLayout(self.thumb_frame)
        tf_layout.setContentsMargins(0, 0, 0, 0)

        self.thumb_label = QLabel()
        self.thumb_label.setObjectName("thumbImage")
        self.thumb_label.setAlignment(Qt.AlignCenter)
        tf_layout.addWidget(self.thumb_label)

        # 表紙左上のお気に入りシンボル・しおりシンボル（リスト用）
        self.fav_badge = _make_badge("★", "favBadge", 18, self.thumb_frame)
        self.bookmark_badge = _make_badge("🔖", "bookmarkBadge", 18, self.thumb_frame)
        self._update_badges()

        self._load_thumbnail()
        self._setup_bookmarks()
        layout.addWidget(self.thumb_frame)

        # 2. 右側情報カラム
        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 2, 0, 2)
        info_layout.setSpacing(4)

        # 2.1 タイトル行 + しおりバッジ
        top_row = QHBoxLayout()
        self.title_label = QLabel(self.title_text)
        self.title_label.setObjectName("listTitle")
        self.title_label.setTextFormat(Qt.PlainText)
        top_row.addWidget(self.title_label)
        top_row.addStretch()

        if self.tags:
            first_tag = self.tags[0]
            tag_badge = PillTag(first_tag, is_checkable=False)
            top_row.addWidget(tag_badge)
        info_layout.addLayout(top_row)

        # 2.2 システム名
        self.sys_label = QLabel(self.system_text)
        self.sys_label.setObjectName("listSystem")
        self.sys_label.setTextFormat(Qt.PlainText)
        info_layout.addWidget(self.sys_label)

        # 2.3 人数・時間
        meta_parts = []
        if self.players_text:
            meta_parts.append(f"人数: {self.players_text}")
        if self.duration_text:
            meta_parts.append(f"時間: {self.duration_text}")
        meta_str = " │ ".join(meta_parts) if meta_parts else "情報未設定"
        self.meta_label = QLabel(meta_str)
        self.meta_label.setObjectName("listMeta")
        self.meta_label.setTextFormat(Qt.PlainText)
        info_layout.addWidget(self.meta_label)

        # 2.4 概要抜粋（1行）
        if self.overview_text:
            clean_ov = self.overview_text.replace("\n", " ")[:40] + "…"
            self.ov_label = QLabel(clean_ov)
            self.ov_label.setObjectName("listOverview")
            self.ov_label.setTextFormat(Qt.PlainText)
            # 長い抜粋でカードが列幅より広がらないよう、幅は列に合わせて収まらない分は切る
            self.ov_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            info_layout.addWidget(self.ov_label)

        info_layout.addStretch()
        layout.addLayout(info_layout)

        self._update_appearance()

    def _load_thumbnail(self):
        if _is_image_data(self.thumb_bytes):
            image = render_list_cover(self.thumb_bytes)
            if image is not None:
                self.cover_loaded = True
                self.thumb_label.setPixmap(QPixmap.fromImage(image))
                return
        self.thumb_label.setPixmap(_list_placeholder())

    @property
    def needs_cover(self):
        """書架のバックグラウンド読み込みで表紙を届ける必要があるか"""
        return bool(self.thumb_key) and not self.cover_loaded

    def set_cover_image(self, image, conflict=False):
        """バックグラウンドで作った表紙（QImage）を反映する"""
        self.cover_loaded = True
        if image is not None and not image.isNull():
            self.thumb_label.setPixmap(QPixmap.fromImage(image))

    def _update_appearance(self):
        active = bool(self.is_hovered or self.is_selected)
        if active == self._applied_active:
            return
        first = self._applied_active is None
        self._applied_active = active
        self.setProperty("active", _bool_prop(active))
        if not first:
            _repolish(self, self.thumb_frame, self.title_label, self.sys_label)

    def set_selected(self, selected):
        self.is_selected = selected
        self._update_appearance()

    def _update_badges(self):
        self.fav_badge.setVisible(self.is_favorite)
        self.bookmark_badge.setVisible(self.is_bookmarked)

        cur_x = 4
        if self.is_favorite:
            self.fav_badge.move(cur_x, 4)
            cur_x += 21
        if self.is_bookmarked:
            self.bookmark_badge.move(cur_x, 4)

    def set_favorite(self, is_fav):
        self.is_favorite = is_fav
        self._update_badges()

    def set_bookmarked(self, is_bm):
        self.is_bookmarked = is_bm
        self._update_badges()

    def set_global_tags(self, global_tags):
        self.global_tags = global_tags or []
        self._setup_bookmarks()

    def _setup_bookmarks(self):
        """表紙右上にグローバルタグと同色のしおりリボンを配置（リスト用）"""
        for rb in getattr(self, "bookmark_ribbons", []):
            rb.setParent(None)
            rb.deleteLater()
        self.bookmark_ribbons = []

        if not self.global_tags:
            return

        tw = 95
        rw, rh = 12, 22
        right_margin = 4
        spacing = 2

        # 優先順序（CoC > マダミス > 未通過 > 通過済 > GM可）で右端から左へ順に並べる
        for i, (tname, tcolor) in enumerate(_ribbon_entries(self.global_tags)):
            x = tw - right_margin - (i + 1) * rw - i * spacing
            if x < 26:  # 左上のお気に入りバッジと重ならないよう制限
                break

            ribbon = BookmarkRibbon(tcolor, tag_name=tname, width=rw, height=rh, parent=self.thumb_frame)
            ribbon.move(x, 0)
            ribbon.show()
            self.bookmark_ribbons.append(ribbon)

    def enterEvent(self, event):
        self.is_hovered = True
        self._update_appearance()
        self.hover_entered.emit(self.item)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.is_hovered = False
        self._update_appearance()
        self.hover_left.emit(self.item)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.item_id)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit(self.item_id)
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        self.context_menu_requested.emit(self.item_id, event.globalPos())
