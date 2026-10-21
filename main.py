import os
import io
import json
import sqlite3
import zipfile
import sys
import ctypes
import shutil
import subprocess
import threading
import time
import webbrowser
import re
import math
import hashlib
import unicodedata
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import tkinter.font as tkfont
from PIL import Image, ImageTk, ImageDraw

try:
    import windnd
except ImportError:
    windnd = None

import notion_sync
import app_settings
from rust_gfx import (
    _ART,
    BAY_BOARD,
    BAY_SIDE,
    CROWN_H,
    _rgba,
    _indicator_image,
    pill_photo,
    pill_label,
    wood_texture,
    bay_photo,
    crown_photo,
    classic_cover,
    book_photo,
    cover_image,
    shade_band_photo,
    book_shadow_photo,
    ribbon_photo,
    plate_photo,
    index_card_photo,
    page_image,
    leather_desk,
    turning_page,
    glow_photo,
    ornament_photo,
    icon_photo,
    reload_gfx_lib,
)

# 画像展開爆弾（DecompressionBomb）のクラッシュ防止
Image.MAX_IMAGE_PIXELS = 17895697

DB_PATH = "catalog.db"
RUST_ROOT = None


# ==============================================================================
# 0. 見た目（色・文字・部品の形）
# ==============================================================================
class C:
    BG = "#0c0907"
    SIDEBAR = "#120d09"
    SURFACE = "#19120c"
    SURFACE_2 = "#221911"
    SUBTLE = "#1e160f"
    BORDER = "#312318"
    BORDER_STRONG = "#443021"
    TEXT = "#e8dcce"
    MUTED = "#9e8e7c"
    FAINT = "#6b5e50"
    ACCENT = "#967942"
    ACCENT_HOVER = "#a88a50"
    ACCENT_PRESSED = "#7f6434"
    ACCENT_DISABLED = "#45361b"
    ACCENT_SOFT = "#22170e"
    ACCENT_TEXT = "#be9f65"
    ON_ACCENT = "#120b05"
    GLOW = "#c4a974"
    HOVER = "#2b1e14"
    PRESSED = "#38271a"
    TAG_BG = "#22170e"
    TAG_FG = "#be9f65"
    STAR = "#be9f65"
    RIBBON = "#9e2a2b"
    SEAL = "#c0392b"
    WARN = "#c98f48"
    DANGER = "#c96658"
    DANGER_SOFT = "#3a1d1a"
    SCROLL = "#312318"
    SCROLL_HOVER = "#443021"
    LINK = "#be9f65"
    PURPLE = "#a580e6"
    PAPER = "#f1e8d2"
    PAPER_2 = "#e7dcc0"
    PAPER_LINE = "#d8caa8"
    INK = "#2b2017"
    INK_MUTED = "#6b5a45"
    INK_FAINT = "#9a8a70"
    BURGUNDY = "#7b2d26"
    BURGUNDY_HOVER = "#93372f"


FONT = "AppFont"
FONT_SMALL = "AppSmall"
FONT_CAPTION = "AppCaption"
FONT_BOLD = "AppBold"
FONT_SMALL_BOLD = "AppSmallBold"
FONT_TITLE = "AppTitle"
FONT_HEADING = "AppHeading"
FONT_LINK = "AppLink"
FONT_BRAND = "AppBrand"
FONT_NAV = "AppNav"
FONT_CAPS = "AppCaps"
FONT_BOOK = "AppBook"
FONT_BOOK_SMALL = "AppBookSmall"
FONT_PANEL_TITLE = "AppPanelTitle"
FONT_SERIF = "AppSerif"
FONT_SERIF_SMALL = "AppSerifSmall"
FONT_SERIF_BOLD = "AppSerifBold"
FONT_LABEL = "AppLabel"
FONT_PAGE_TITLE = "AppPageTitle"
FONT_NORMAL = FONT
FONT_NORMAL_BOLD = FONT_BOLD

FONT_FAMILIES = ("Yu Gothic UI", "Meiryo UI", "BIZ UDPGothic", "Meiryo", "Hiragino Sans", "Noto Sans CJK JP", "Noto Sans JP")
SERIF_FAMILIES = ("Yu Mincho", "游明朝", "Yu Mincho Demibold", "BIZ UDPMincho", "BIZ UDP明朝 Medium", "MS PMincho",
                  "ＭＳ Ｐ明朝", "Hiragino Mincho ProN", "Noto Serif CJK JP", "Noto Serif JP")


def _pick_family(root, candidates=FONT_FAMILIES):
    families = set(tkfont.families(root))
    for f in candidates:
        if f in families:
            return f
    return tkfont.nametofont("TkDefaultFont", root).actual("family")


_FONTS = {}
_IMAGES = {}





def _image_elements(root, s):
    scale = max(1.0, root.winfo_fpixels("1i") / 96)
    size = round(16 * scale)
    for kind in ("check", "radio"):
        img = lambda fill, border, mark=None: _indicator_image(root, kind, size, fill, border, mark, gap=round(7 * scale))
        off = img(C.SURFACE_2, C.BORDER_STRONG)
        name = f"App.{kind}.indicator"
        if name not in s.element_names():
            s.element_create(
                name, "image", off,
                ("disabled", "selected", img(C.ACCENT_DISABLED, C.ACCENT_DISABLED, C.ON_ACCENT)),
                ("disabled", img(C.SUBTLE, C.BORDER)),
                ("pressed", "selected", img(C.ACCENT_PRESSED, C.ACCENT_PRESSED, C.ON_ACCENT)),
                ("active", "selected", img(C.ACCENT_HOVER, C.ACCENT_HOVER, C.ON_ACCENT)),
                ("selected", img(C.ACCENT, C.ACCENT, C.ON_ACCENT)),
                ("active", img(C.SURFACE_2, C.FAINT)),
                sticky="",
            )
    s.layout("TCheckbutton", [("Checkbutton.padding", {"sticky": "nswe", "children": [
        ("App.check.indicator", {"side": "left", "sticky": ""}),
        ("Checkbutton.focus", {"side": "left", "sticky": "w", "children": [("Checkbutton.label", {"sticky": "nswe"})]})]})])
    s.layout("TRadiobutton", [("Radiobutton.padding", {"sticky": "nswe", "children": [
        ("App.radio.indicator", {"side": "left", "sticky": ""}),
        ("Radiobutton.focus", {"side": "left", "sticky": "w", "children": [("Radiobutton.label", {"sticky": "nswe"})]})]})])

    chevron = lambda color: _indicator_image(root, "chevron", size, color, color)
    if "App.chevron" not in s.element_names():
        s.element_create("App.chevron", "image", chevron(C.MUTED), ("disabled", chevron(C.FAINT)),
                         sticky="", padding=(round(4 * scale), 0, round(8 * scale), 0))
    s.layout("TCombobox", [("Entry.field", {"sticky": "nswe", "children": [
        ("App.chevron", {"side": "right", "sticky": ""}),
        ("Combobox.padding", {"sticky": "nswe", "children": [("Combobox.textarea", {"sticky": "nswe"})]})]})])


def _make_font(root, name, **opts):
    try:
        tkfont.nametofont(name, root).configure(**opts)
    except tk.TclError:
        _FONTS[name] = tkfont.Font(root, name=name, **opts)


def apply_theme(root):
    _ART.clear()
    _IMAGES.clear()
    family = _pick_family(root)
    serif = _pick_family(root, SERIF_FAMILIES + FONT_FAMILIES)
    for name, size, weight in [
        (FONT_BRAND, 16, "bold"), (FONT_NAV, 12, "normal"), (FONT_PANEL_TITLE, 16, "bold"), (FONT_SERIF, 11, "normal"),
        (FONT_SERIF_SMALL, 9, "normal"), (FONT_SERIF_BOLD, 11, "bold"), (FONT_LABEL, 9, "bold"), (FONT_PAGE_TITLE, 18, "bold"),
        (FONT_BOOK, 10, "bold"), (FONT_BOOK_SMALL, 9, "bold"),
    ]:
        _make_font(root, name, family=serif, size=size, weight=weight, underline=0)
    for name, size, weight, underline in [
        (FONT, 10, "normal", 0), (FONT_SMALL, 9, "normal", 0), (FONT_CAPTION, 8, "normal", 0),
        (FONT_BOLD, 10, "bold", 0), (FONT_SMALL_BOLD, 9, "bold", 0), (FONT_TITLE, 12, "bold", 0),
        (FONT_HEADING, 15, "bold", 0), (FONT_LINK, 8, "normal", 1), (FONT_CAPS, 10, "bold", 0),
    ]:
        _make_font(root, name, family=family, size=size, weight=weight, underline=underline)

    root.configure(background=C.BG)
    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure(
        ".", background=C.SURFACE, foreground=C.TEXT, font=FONT, bordercolor=C.BORDER_STRONG,
        lightcolor=C.SURFACE, darkcolor=C.SURFACE, troughcolor=C.BG, focuscolor=C.ACCENT,
        selectbackground=C.ACCENT_SOFT, selectforeground=C.TEXT, insertcolor=C.TEXT,
        fieldbackground=C.SURFACE, arrowcolor=C.MUTED,
    )
    s.map(".", foreground=[("disabled", C.FAINT)])
    _image_elements(root, s)

    s.configure("TCheckbutton", background=C.SURFACE, foreground=C.TEXT)
    s.map("TCheckbutton",
          background=[("active", C.SURFACE), ("pressed", C.SURFACE), ("disabled", C.SURFACE)],
          foreground=[("disabled", C.FAINT), ("active", C.TEXT)])

    s.configure("App.TCheckbutton", background=C.BG, foreground=C.TEXT)
    s.map("App.TCheckbutton",
          background=[("active", C.BG), ("pressed", C.BG), ("disabled", C.BG)],
          foreground=[("disabled", C.FAINT), ("active", C.TEXT)])

    s.configure("Card.TCheckbutton", background=C.SURFACE_2, foreground=C.TEXT)
    s.map("Card.TCheckbutton",
          background=[("active", C.SURFACE_2), ("pressed", C.SURFACE_2), ("disabled", C.SURFACE_2)],
          foreground=[("disabled", C.FAINT), ("active", C.TEXT)])

    s.configure("TRadiobutton", background=C.SURFACE, foreground=C.TEXT)
    s.map("TRadiobutton",
          background=[("active", C.SURFACE), ("pressed", C.SURFACE), ("disabled", C.SURFACE)],
          foreground=[("disabled", C.FAINT), ("active", C.TEXT)])

    s.configure("App.TRadiobutton", background=C.BG, foreground=C.TEXT)
    s.map("App.TRadiobutton",
          background=[("active", C.BG), ("pressed", C.BG), ("disabled", C.BG)],
          foreground=[("disabled", C.FAINT), ("active", C.TEXT)])

    s.configure("Card.TRadiobutton", background=C.SURFACE_2, foreground=C.TEXT)
    s.map("Card.TRadiobutton",
          background=[("active", C.SURFACE_2), ("pressed", C.SURFACE_2), ("disabled", C.SURFACE_2)],
          foreground=[("disabled", C.FAINT), ("active", C.TEXT)])

    s.configure("App.TFrame", background=C.BG)
    s.configure("Bordered.TFrame", background=C.SURFACE, borderwidth=1, relief="solid", bordercolor=C.BORDER)
    s.configure("App.TLabel", background=C.BG)
    s.configure("AppMuted.TLabel", background=C.BG, foreground=C.MUTED, font=FONT_SMALL)
    s.configure("AppSection.TLabel", background=C.BG, foreground=C.TEXT, font=FONT_SMALL_BOLD)
    s.configure("Muted.TLabel", foreground=C.MUTED)
    s.configure("Hint.TLabel", foreground=C.MUTED, font=FONT_SMALL)
    s.configure("Heading.TLabel", font=FONT_HEADING)
    s.configure("Title.TLabel", font=FONT_SERIF_BOLD)
    s.configure("Section.TLabel", font=FONT_BOLD)
    s.configure("TSeparator", background=C.BORDER)

    def button(style, bg, fg, border, hover, pressed, disabled_bg, disabled_fg, padding=(14, 6), font=FONT, hover_border=None):
        s.configure(style, background=bg, foreground=fg, bordercolor=border, lightcolor=bg, darkcolor=bg,
                    padding=padding, font=font, anchor="center", focusthickness=0, relief="raised")
        states = [("disabled", disabled_bg), ("pressed", pressed), ("active", hover)]
        s.map(style, background=states, lightcolor=states, darkcolor=states,
              foreground=[("disabled", disabled_fg)],
              bordercolor=[("disabled", disabled_bg if bg not in (C.SURFACE, C.SURFACE_2) else C.BORDER),
                           ("focus", C.ACCENT), ("active", hover_border or border)],
              relief=[("pressed", "raised")])

    button("TButton", C.SURFACE_2, C.TEXT, C.BORDER_STRONG, C.HOVER, C.PRESSED, C.SURFACE_2, C.FAINT, hover_border=C.FAINT)
    button("Accent.TButton", C.ACCENT, C.ON_ACCENT, C.ACCENT, C.ACCENT_HOVER, C.ACCENT_PRESSED, C.ACCENT_DISABLED, C.FAINT,
           font=FONT_BOLD, hover_border=C.ACCENT_HOVER)
    button("Small.TButton", C.SURFACE_2, C.TEXT, C.BORDER_STRONG, C.HOVER, C.PRESSED, C.SURFACE_2, C.FAINT, padding=(8, 2),
           font=FONT_SMALL, hover_border=C.FAINT)
    button("Danger.Small.TButton", C.SURFACE_2, C.DANGER, C.BORDER_STRONG, C.DANGER_SOFT, C.DANGER_SOFT, C.SURFACE_2, C.FAINT,
           padding=(8, 2), font=FONT_SMALL, hover_border=C.DANGER)
    button("Ghost.TButton", C.SURFACE, C.ACCENT_TEXT, C.SURFACE, C.ACCENT_SOFT, C.PRESSED, C.SURFACE, C.FAINT, padding=(8, 4))
    button("Side.TButton", C.SIDEBAR, C.MUTED, C.SIDEBAR, C.HOVER, C.PRESSED, C.SIDEBAR, C.FAINT, padding=(10, 5), font=FONT_SMALL)
    button("AppGhost.TButton", C.BG, C.ACCENT_TEXT, C.BG, C.PRESSED, C.BORDER, C.BG, C.FAINT, padding=(8, 2), font=FONT_SMALL)

    s.configure("TEntry", padding=(8, 5), fieldbackground=C.SURFACE_2, bordercolor=C.BORDER_STRONG,
                lightcolor=C.SURFACE_2, darkcolor=C.SURFACE_2, foreground=C.TEXT)
    s.map("TEntry", bordercolor=[("focus", C.ACCENT), ("hover", C.FAINT)], lightcolor=[("focus", C.ACCENT)])

    s.configure("Paper.TFrame", background=C.PAPER)
    s.configure("Paper.TLabel", background=C.PAPER, foreground=C.INK)
    s.configure("PaperTitle.TLabel", background=C.PAPER, foreground=C.INK, font=FONT_PAGE_TITLE)
    s.configure("PaperMuted.TLabel", background=C.PAPER, foreground=C.INK_MUTED, font=FONT_SMALL)
    s.configure("PaperCaps.TLabel", background=C.PAPER, foreground=C.BURGUNDY, font=FONT_LABEL)
    button("Paper.TButton", C.PAPER_2, C.INK, "#b9a57e", "#ddd0ae", "#d2c39d", C.PAPER_2, C.INK_FAINT, padding=(12, 5),
           hover_border=C.INK_MUTED)
    button("PaperAccent.TButton", C.BURGUNDY, C.PAPER, C.BURGUNDY, C.BURGUNDY_HOVER, "#6a2620", "#b98f88", C.PAPER,
           font=FONT_BOLD, padding=(12, 6), hover_border=C.BURGUNDY_HOVER)

    for name, base in (("PaperSeg.Toolbutton", C.PAPER_2), ("PaperChip.Toolbutton", C.PAPER_2)):
        s.configure(name, background=base, foreground=C.INK_MUTED, bordercolor="#b9a57e", lightcolor=base, darkcolor=base,
                    padding=(10, 4), font=FONT_SMALL_BOLD, relief="raised", anchor="center", focusthickness=0)
        st = [("selected", C.BURGUNDY), ("active", "#ddd0ae")]
        s.map(name, background=st, lightcolor=st, darkcolor=st, bordercolor=[("selected", C.BURGUNDY)],
              foreground=[("selected", C.PAPER), ("active", C.INK)],
              relief=[("selected", "raised"), ("pressed", "raised"), ("active", "raised")])

    s.configure("Seg.Toolbutton", background=C.SURFACE_2, foreground=C.MUTED, bordercolor=C.SURFACE_2,
                lightcolor=C.SURFACE_2, darkcolor=C.SURFACE_2, padding=(14, 5), font=FONT_BOLD, relief="raised",
                anchor="center", focusthickness=0)
    seg = [("selected", C.ACCENT_SOFT), ("active", C.HOVER)]
    s.map("Seg.Toolbutton", background=seg, lightcolor=seg, darkcolor=seg, bordercolor=seg,
          foreground=[("selected", C.ACCENT_TEXT), ("active", C.TEXT)],
          relief=[("selected", "raised"), ("pressed", "raised"), ("active", "raised")])

    s.configure("Ledger.Treeview", background=C.PAPER, fieldbackground=C.PAPER, foreground=C.INK, rowheight=52,
                bordercolor=C.PAPER_LINE, lightcolor=C.PAPER, darkcolor=C.PAPER, font=FONT)
    s.map("Ledger.Treeview", background=[("selected", "#d9c49a")], foreground=[("selected", C.INK)])
    s.configure("Ledger.Treeview.Heading", background="#3a2a1c", foreground=C.ACCENT_TEXT, font=FONT_LABEL,
                lightcolor="#3a2a1c", darkcolor="#3a2a1c", bordercolor="#2a1d12", padding=(8, 7), relief="flat")

    root.bind_all("<MouseWheel>", _on_mousewheel, add="+")
    root.bind_all("<Button-4>", _on_mousewheel, add="+")
    root.bind_all("<Button-5>", _on_mousewheel, add="+")
    apply_window_titlebar_theme(root)


def apply_window_titlebar_theme(window, caption_color_hex=None, text_color_hex=None, borderless=False):
    """Windows 11 / 10 のタイトルバーをアプリ本体の色に合わせ、アプリ名やボタンも背景色に同化させる。"""
    if sys.platform != "win32":
        return
    caption_color_hex = caption_color_hex or C.BG
    text_color_hex = text_color_hex or "#261a12"
    try:
        window.update_idletasks()
        hwnd = window.winfo_id()
        root_hwnd = ctypes.windll.user32.GetAncestor(hwnd, 2)
        if root_hwnd:
            hwnd = root_hwnd

        # 1. ダークモード化 (DWMWA_USE_IMMERSIVE_DARK_MODE = 20, 19)
        val = ctypes.c_int(1)
        res = ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(val), ctypes.sizeof(val))
        if res != 0:
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(val), ctypes.sizeof(val))

        def to_colorref(hex_str):
            s = hex_str.lstrip("#")
            r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
            return (b << 16) | (g << 8) | r

        # 2. タイトルバー背景色 (DWMWA_CAPTION_COLOR = 35)
        cap_val = ctypes.c_uint32(to_colorref(caption_color_hex))
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(cap_val), ctypes.sizeof(cap_val))

        # 3. タイトルバー文字色 (DWMWA_TEXT_COLOR = 36)
        txt_val = ctypes.c_uint32(to_colorref(text_color_hex))
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(txt_val), ctypes.sizeof(txt_val))

        # 4. ウィンドウ境界線色 (DWMWA_BORDER_COLOR = 34)
        border_val = ctypes.c_uint32(to_colorref(C.BORDER))
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(border_val), ctypes.sizeof(border_val))

        # 5. ボーダーレス化（ネイティブリサイズ枠・タスクバーを維持しつつ標準タイトルバーを除去）
        if borderless:
            GWL_STYLE = -16
            WS_CAPTION = 0x00C00000
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
            if style & WS_CAPTION:
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, style & ~WS_CAPTION)
                SWP_FRAMECHANGED = 0x0020
                SWP_NOMOVE = 0x0002
                SWP_NOSIZE = 0x0001
                SWP_NOZORDER = 0x0004
                ctypes.windll.user32.SetWindowPos(
                    hwnd, 0, 0, 0, 0, 0,
                    SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER
                )
    except Exception:
        pass


def get_saved_geometry(key, default_w, default_h):
    """INIファイルから保存されたジオメトリを取得（画面内バリデーション付き）"""
    try:
        s = settings_store()
        raw = s.get("window", f"{key}_geometry")
        if raw and "x" in raw and "+" in raw:
            parts = raw.replace("+", "x+").replace("-", "x-").split("x")
            if len(parts) >= 3:
                w, h = int(parts[0]), int(parts[1])
                x, y = int(parts[2]), int(parts[3])
                # 画面内にあるか確認
                return f"{w}x{h}+{x}+{y}"
    except Exception:
        pass
    return None


def save_geometry(key, window):
    """現在のウィンドウ位置・サイズをINIファイルに記録"""
    try:
        s = settings_store()
        geom = window.geometry()
        s.set("window", f"{key}_geometry", geom, save=False)
        is_max = 1 if hasattr(window, "state") and window.state() == "zoomed" else 0
        s.set("window", f"{key}_maximized", str(is_max), save=True)
    except Exception:
        pass


def center_on_screen(window, default_w=1200, default_h=800):
    """ウィンドウをディスプレイの中央に配置"""
    window.update_idletasks()
    sw = window.winfo_screenwidth()
    sh = window.winfo_screenheight()
    w = min(default_w, max(600, int(sw * 0.9)))
    h = min(default_h, max(400, int(sh * 0.9)))
    x = max(0, (sw - w) // 2)
    y = max(0, (sh - h) // 2)
    window.geometry(f"{w}x{h}+{x}+{y}")


def center_on_parent(window, parent, default_w=940, default_h=800):
    """ポップアップウィンドウを親ウィンドウの中央に正確に配置"""
    try:
        window.update_idletasks()
    except Exception:
        pass

    if parent is not None:
        try:
            parent.update_idletasks()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            px = parent.winfo_x()
            py = parent.winfo_y()
            if pw > 80 and ph > 80:
                x = px + (pw - default_w) // 2
                y = py + (ph - default_h) // 2
                window.geometry(f"{default_w}x{default_h}+{x}+{y}")
                return
        except Exception:
            pass

    # 親の情報が取得できない場合のフォールバック（画面中央）
    try:
        sw = window.winfo_screenwidth()
        sh = window.winfo_screenheight()
        x = max(0, (sw - default_w) // 2)
        y = max(0, (sh - default_h) // 2)
        window.geometry(f"{default_w}x{default_h}+{x}+{y}")
    except Exception:
        window.geometry(f"{default_w}x{default_h}")


class CustomTitleBar(tk.Frame):
    """Antigravity スタイルのカスタムタイトルバー（背景同化ボタン付き）"""
    HEIGHT = 30

    def __init__(self, parent, root, title_text="グリモワールシェルフ", is_dialog=False, geom_key="main"):
        super().__init__(parent, background=C.BG, height=self.HEIGHT)
        self.root = root
        self.is_dialog = is_dialog
        self.geom_key = geom_key
        self.pack(side=tk.TOP, fill=tk.X)
        self.pack_propagate(False)

        self._drag_start_x = 0
        self._drag_start_y = 0
        self.title_text = title_text

        self._setup_ui()

    def _setup_ui(self):
        # 左側余白
        left_pad = tk.Frame(self, background=C.BG, width=12)
        left_pad.pack(side=tk.LEFT)

        if self.is_dialog:
            self.lbl_icon = tk.Label(
                self, text="✒", font=("Segoe UI", 10),
                foreground="#5a8fd8", background=C.BG
            )
            self.lbl_icon.pack(side=tk.LEFT, padx=(2, 4))

        # アプリタイトル (背景と同化する控えめな色)
        self.lbl_title = tk.Label(
            self, text=self.title_text, font=FONT_CAPTION,
            foreground=C.BORDER_STRONG, background=C.BG
        )
        self.lbl_title.pack(side=tk.LEFT, padx=6)

        # ドラッグ用の中央透過領域
        self.drag_area = tk.Frame(self, background=C.BG)
        self.drag_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 右側システムボタン群 (最小化, 最大化/復元, 閉じる)
        btn_box = tk.Frame(self, background=C.BG)
        btn_box.pack(side=tk.RIGHT)

        def make_btn(text, cmd, is_close=False):
            # 通常時は背景に完全に溶け込む暗い色
            btn = tk.Label(
                btn_box, text=text, font=("Segoe UI", 9),
                foreground=C.BORDER_STRONG, background=C.BG,
                width=5, height=1, cursor="hand2"
            )

            def on_enter(e):
                if is_close:
                    btn.configure(background=C.BURGUNDY, foreground=C.TEXT)
                else:
                    btn.configure(background=C.SURFACE_2, foreground=C.TEXT)

            def on_leave(e):
                btn.configure(background=C.BG, foreground=C.BORDER_STRONG)

            btn.bind("<Enter>", on_enter)
            btn.bind("<Leave>", on_leave)
            btn.bind("<Button-1>", lambda e: cmd())
            btn.pack(side=tk.LEFT, fill=tk.Y)
            return btn

        if not self.is_dialog:
            self.btn_min = make_btn("—", self._on_minimize)
            self.btn_max = make_btn("□", self._on_maximize_toggle)
        self.btn_close = make_btn("✕", self._on_close, is_close=True)

        # ドラッグ移動とダブルクリック最大化のバインド
        self._is_dragging = False
        self._root_hwnd = None
        drag_widgets = [self, self.lbl_title, self.drag_area, left_pad]
        if self.is_dialog and hasattr(self, "lbl_icon"):
            drag_widgets.append(self.lbl_icon)
        for w in drag_widgets:
            w.bind("<Button-1>", self._start_drag)
            w.bind("<B1-Motion>", self._do_drag)
            w.bind("<ButtonRelease-1>", self._stop_drag)
            if not self.is_dialog:
                w.bind("<Double-Button-1>", lambda e: self._on_maximize_toggle())

    def _start_drag(self, e):
        if hasattr(self, "btn_max") and self.root.state() == "zoomed":
            self.root.state("normal")
            self.btn_max.config(text="□")
            self.root.update_idletasks()

        self._is_dragging = True
        self.root._is_window_dragging = True
        self._start_mouse_x = e.x_root
        self._start_mouse_y = e.y_root

        if sys.platform == "win32":
            try:
                hwnd = self.root.winfo_id()
                root_hwnd = ctypes.windll.user32.GetAncestor(hwnd, 2) or hwnd
                class RECT(ctypes.Structure):
                    _fields_ = [('left', ctypes.c_long), ('top', ctypes.c_long), ('right', ctypes.c_long), ('bottom', ctypes.c_long)]
                r = RECT()
                ctypes.windll.user32.GetWindowRect(root_hwnd, ctypes.byref(r))
                self._start_win_x = r.left
                self._start_win_y = r.top
                self._start_win_w = r.right - r.left
                self._start_win_h = r.bottom - r.top
                self._root_hwnd = root_hwnd
            except Exception:
                self._start_win_x = self.root.winfo_x()
                self._start_win_y = self.root.winfo_y()
                self._start_win_w = self.root.winfo_width()
                self._start_win_h = self.root.winfo_height()
                self._root_hwnd = None
        else:
            self._start_win_x = self.root.winfo_x()
            self._start_win_y = self.root.winfo_y()
            self._start_win_w = self.root.winfo_width()
            self._start_win_h = self.root.winfo_height()
            self._root_hwnd = None

        self._last_drag_time = 0

    def _do_drag(self, e):
        if not self._is_dragging:
            return
        now = time.monotonic()
        if now - self._last_drag_time < 0.008:
            return
        self._last_drag_time = now

        dx = e.x_root - self._start_mouse_x
        dy = e.y_root - self._start_mouse_y
        if dx == 0 and dy == 0:
            return
        new_x = self._start_win_x + dx
        new_y = self._start_win_y + dy

        if sys.platform == "win32" and self._root_hwnd:
            try:
                SWP_NOSIZE = 0x0001
                SWP_NOZORDER = 0x0004
                SWP_NOACTIVATE = 0x0010
                user32 = ctypes.windll.user32
                user32.SetWindowPos.argtypes = [
                    ctypes.c_void_p, ctypes.c_void_p,
                    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                    ctypes.c_uint
                ]
                user32.SetWindowPos.restype = ctypes.c_int
                user32.SetWindowPos(self._root_hwnd, None, new_x, new_y, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
                return
            except Exception:
                pass

        self.root.geometry(f"{self._start_win_w}x{self._start_win_h}+{new_x}+{new_y}")

    def _stop_drag(self, e):
        if not self._is_dragging:
            return
        self._is_dragging = False
        self.root._is_window_dragging = False

        if sys.platform == "win32" and self._root_hwnd:
            try:
                class RECT(ctypes.Structure):
                    _fields_ = [('left', ctypes.c_long), ('top', ctypes.c_long), ('right', ctypes.c_long), ('bottom', ctypes.c_long)]
                r = RECT()
                ctypes.windll.user32.GetWindowRect(self._root_hwnd, ctypes.byref(r))
                w = self.root.winfo_width()
                h = self.root.winfo_height()
                self.root.geometry(f"{w}x{h}+{r.left}+{r.top}")
            except Exception:
                pass

        save_geometry(getattr(self, "geom_key", "main"), self.root)

    def _on_minimize(self):
        self.root.iconify()

    def _on_maximize_toggle(self):
        if hasattr(self, "btn_max"):
            if self.root.state() == "zoomed":
                self.root.state("normal")
                self.btn_max.config(text="□")
            else:
                self.root.state("zoomed")
                self.btn_max.config(text="❐")

    def _on_close(self):
        if hasattr(self.root, "_on_close"):
            self.root._on_close()
        elif hasattr(self.root, "on_exit"):
            self.root.on_exit()
        else:
            self.root.destroy()


def _on_mousewheel(event):
    try:
        w = event.widget.winfo_containing(event.x_root, event.y_root)
    except (tk.TclError, AttributeError, KeyError):
        return
    while w is not None:
        if isinstance(w, (tk.Text, tk.Listbox, ttk.Treeview, ttk.Combobox)):
            return
        if isinstance(w, tk.Canvas) and w.cget("yscrollcommand"):
            if tuple(w.yview()) == (0.0, 1.0):
                return
            up = event.num == 4 or getattr(event, "delta", 0) > 0
            step = 3 if str(w.cget("yscrollincrement")) not in ("0", "0.0") else 1
            w.yview_scroll(-step if up else step, "units")
            return
        w = w.master


class FlowFrame(ttk.Frame):
    def __init__(self, parent, hgap=6, vgap=6, **kw):
        super().__init__(parent, **kw)
        self.hgap, self.vgap = hgap, vgap
        self.items = []
        self.bind("<Configure>", lambda e: self.layout(e.width))

    def add(self, widget):
        self.items.append(widget)
        return widget

    def clear(self):
        for w in self.items:
            w.destroy()
        self.items = []
        self.configure(height=1)

    def layout(self, width=None):
        width = width or self.winfo_width()
        if width <= 1:
            try:
                width = max(self.master.winfo_width() - 40, 600)
            except Exception:
                width = 600
        x = y = row_h = 0
        for w in self.items:
            ww, wh = w.winfo_reqwidth(), w.winfo_reqheight()
            if x > 0 and x + ww > width:
                x, y, row_h = 0, y + row_h + self.vgap, 0
            w.place(x=x, y=y)
            x += ww + self.hgap
            row_h = max(row_h, wh)
        height = max(y + row_h, 1)
        if int(str(self.cget("height") or 0)) != height:
            self.configure(height=height)


def pin_bottom_bar(bar):
    win = bar.master
    bar.configure(padding=(16, 10))
    bar.pack(side=tk.BOTTOM, fill=tk.X)
    tk.Frame(win, height=1, background=C.BORDER).pack(side=tk.BOTTOM, fill=tk.X)


# ==============================================================================
# 0.5 画像生成・エフェクト処理（rust_gfx モジュールに移譲）
# ==============================================================================
# ※ 木目テクスチャ、ドロップシャドウ、ページめくり変形、本棚パーツ、カバー描画等の
#    画像処理は rust_gfx.py (Rust DLL: cover_extractor.dll) に集約・独立化されています。




# ==============================================================================
# 1. Rust DLL 呼び出し
# ==============================================================================
class CoverExtractorError(Exception):
    pass


def _library_name():
    if sys.platform == "win32":
        return "cover_extractor.dll"
    if sys.platform == "darwin":
        return "libcover_extractor.dylib"
    return "libcover_extractor.so"


def _app_dir():
    return os.path.dirname(os.path.abspath(__file__))


def _library_candidates():
    candidates = []
    if os.environ.get("COVER_EXTRACTOR_DLL"):
        candidates.append(os.environ["COVER_EXTRACTOR_DLL"])
    candidates.append(os.path.join(_app_dir(), _library_name()))
    return candidates


def _source_root(rust_root):
    candidates = []
    if os.environ.get("COVER_EXTRACTOR_SRC"):
        candidates.append(os.environ["COVER_EXTRACTOR_SRC"])
    if rust_root:
        candidates.append(rust_root)
    candidates.append(_app_dir())
    for c in candidates:
        if os.path.isfile(os.path.join(c, "Cargo.toml")):
            return c
    raise CoverExtractorError(
        "DLL がなく、ビルドするための Rust のソースも見つかりません（Cargo.toml がありません）。"
    )


def _find_cargo():
    found = shutil.which("cargo")
    if found:
        return found
    home = os.environ.get("CARGO_HOME") or os.path.join(os.path.expanduser("~"), ".cargo")
    exe = "cargo.exe" if sys.platform == "win32" else "cargo"
    path = os.path.join(home, "bin", exe)
    return path if os.path.isfile(path) else None


def _build_library_from_source(rust_root):
    rust_root = _source_root(rust_root)
    cargo = _find_cargo()
    if not cargo:
        raise CoverExtractorError("DLL がなく、ソースからビルドするための cargo も見つかりません。")
    cmd = [cargo, "rustc", "--release", "--lib", "--features", "pdf", "--crate-type", "cdylib"]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    ret = subprocess.run(
        cmd, cwd=rust_root, capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=flags
    )
    if ret.returncode != 0:
        tail = "\n".join(ret.stderr.strip().splitlines()[-30:])
        raise CoverExtractorError(f"ソースからの DLL のビルドに失敗しました。\n\n{tail}")
    built = os.path.join(rust_root, "target", "release", _library_name())
    if not os.path.isfile(built):
        raise CoverExtractorError(f"ビルドは成功しましたが、DLL が見つかりません: {built}")
    dest = os.path.join(_app_dir(), _library_name())
    tmp = dest + ".tmp"
    try:
        shutil.copy2(built, tmp)
        os.replace(tmp, dest)
    except OSError as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise CoverExtractorError(f"DLL を配置できませんでした: {e}")
    return dest


def _find_library(rust_root):
    res = None
    for c in _library_candidates():
        if os.path.isfile(c):
            res = c
            break
    if res is None:
        res = _build_library_from_source(rust_root)
    reload_gfx_lib()
    return res


class RustDllExtractor:
    MORE_CANDIDATES = 8

    def __init__(self, rust_root=RUST_ROOT, options=None):
        self.lib_path = _find_library(rust_root)
        lib = ctypes.CDLL(self.lib_path)
        p, s = ctypes.c_void_p, ctypes.c_char_p

        lib.ce_version.restype = s
        lib.ce_last_error.restype = s
        lib.ce_extractor_new.argtypes = [s]
        lib.ce_extractor_new.restype = p
        lib.ce_extractor_free.argtypes = [p]
        lib.ce_extractor_free.restype = None
        lib.ce_extract.argtypes = [p, s]
        lib.ce_extract.restype = p
        lib.ce_more_candidates.argtypes = [p, s, s, ctypes.c_uint32]
        lib.ce_more_candidates.restype = p
        lib.ce_extract_info.argtypes = [p, s]
        lib.ce_extract_info.restype = p
        self.has_url = hasattr(lib, "ce_extract_url")
        if self.has_url:
            lib.ce_extract_url.argtypes = [p, s]
            lib.ce_extract_url.restype = p
        lib.ce_result_json.argtypes = [p]
        lib.ce_result_json.restype = p
        lib.ce_result_image_count.argtypes = [p]
        lib.ce_result_image_count.restype = ctypes.c_uint32
        lib.ce_result_image.argtypes = [p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_size_t)]
        lib.ce_result_image.restype = ctypes.c_int32
        lib.ce_result_free.argtypes = [p]
        lib.ce_result_free.restype = None
        self.lib = lib

        opts = json.dumps(options).encode("utf-8") if options else None
        self.handle = lib.ce_extractor_new(opts)
        if not self.handle:
            raise CoverExtractorError(f"抽出器を作れませんでした: {self._last_error()}")

    def close(self):
        if getattr(self, "handle", None):
            self.lib.ce_extractor_free(self.handle)
            self.handle = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def _last_error(self):
        e = self.lib.ce_last_error()
        return e.decode("utf-8", "replace") if e else "unknown error"

    def _take_result(self, handle, what):
        if not handle:
            raise CoverExtractorError(f"{what}: {self._last_error()}")
        try:
            ptr = self.lib.ce_result_json(handle)
            data = json.loads(ctypes.string_at(ptr).decode("utf-8")) if ptr else {}
            images = []
            for i in range(self.lib.ce_result_image_count(handle)):
                buf, size = ctypes.c_void_p(), ctypes.c_size_t()
                if self.lib.ce_result_image(handle, i, ctypes.byref(buf), ctypes.byref(size)) == 0 and buf.value:
                    images.append(ctypes.string_at(buf.value, size.value))
                else:
                    images.append(b"")
            return data, images
        finally:
            self.lib.ce_result_free(handle)

    @staticmethod
    def _path_arg(path):
        return os.fspath(path).encode("utf-8")

    def extract_cover(self, path):
        return self._take_result(self.lib.ce_extract(self.handle, self._path_arg(path)), "表紙の抽出")

    def more_candidates(self, path, exclude, limit):
        ex = json.dumps(list(exclude), ensure_ascii=False).encode("utf-8")
        return self._take_result(
            self.lib.ce_more_candidates(self.handle, self._path_arg(path), ex, limit), "候補の取得"
        )

    def placeholder_jpeg(self):
        if not hasattr(self, "_placeholder"):
            self._placeholder = None
            try:
                cover, images = self.extract_cover(os.path.join(_app_dir(), "__no_such_source__"))
                if cover.get("cover", {}).get("placeholder") and images:
                    self._placeholder = images[0]
            except CoverExtractorError:
                pass
        return self._placeholder

    def extract_url(self, url):
        if not self.has_url:
            raise CoverExtractorError("この DLL は URL からの取得に対応していません。")
        data, images = self._take_result(self.lib.ce_extract_url(self.handle, url.strip().encode("utf-8")), "URL からの取得")
        idx = data.get("image")
        jpeg = images[idx] if idx is not None and idx < len(images) and images[idx] else None
        return data, jpeg

    def extract_info(self, path):
        data, _ = self._take_result(self.lib.ce_extract_info(self.handle, self._path_arg(path)), "情報の抽出")
        return data

    def run_extract(self, target_path):
        thumb_bytes = None
        choices = []
        info_dict = {}

        try:
            cover, images = self.extract_cover(target_path)
            c = cover.get("cover", {})
            for ch in cover.get("choices", []):
                idx = ch.get("image")
                if idx is not None and idx < len(images) and images[idx]:
                    choices.append({"entry_path": ch.get("entry_path", ""), "jpeg": images[idx]})

            if not c.get("placeholder"):
                thumb_bytes = images[c.get("image", 0)] if images else None
            else:
                shown = [ch["entry_path"] for ch in choices]
                more, more_images = self.more_candidates(target_path, shown, self.MORE_CANDIDATES)
                for ch in more.get("candidates", []):
                    idx = ch.get("image")
                    if idx is not None and idx < len(more_images) and more_images[idx]:
                        choices.append({"entry_path": ch.get("entry_path", ""), "jpeg": more_images[idx]})
                if not choices and images:
                    thumb_bytes = images[c.get("image", 0)]
        except CoverExtractorError:
            pass

        try:
            info_dict = self.extract_info(target_path)
        except CoverExtractorError:
            pass

        return thumb_bytes, choices, info_dict


# ==============================================================================
# 1.4 パース・正規化ユーティリティ
# ==============================================================================
def parse_info(info):
    fields = {"title": None, "system_name": None, "players_text": None, "duration_text": None, "overview": None, "synopsis": None}
    auto_tags = []
    if not info:
        return fields, auto_tags

    def value(key):
        obj = info.get(key)
        return obj.get("value") if isinstance(obj, dict) else obj

    title = value("title")
    if title and len(str(title)) >= 2:
        fields["title"] = str(title)[:200]

    system_name = value("system")
    if system_name:
        fields["system_name"] = str(system_name)[:100]
        auto_tags.append(str(system_name)[:100])

    if info.get("players"):
        p_obj = info["players"]
        p_val = value("players")
        raw_text = str(p_obj.get("raw_text", "")).lower() if isinstance(p_obj, dict) else str(p_obj).lower()
        if any(k in raw_text for k in ["gmレス", "kpレス", "ソロ"]):
            auto_tags.append("GMレス")
        if isinstance(p_val, dict):
            min_p, max_p = p_val.get("min"), p_val.get("max")
            if min_p is not None and max_p is not None:
                fields["players_text"] = f"{min_p}〜{max_p}人" if min_p != max_p else f"{min_p}人"
                auto_tags.append(f"{min_p}PL" if min_p == max_p else f"{min_p}〜{max_p}PL")
        elif isinstance(p_val, str):
            fields["players_text"] = p_val[:50]
            digits = [int(d) for d in re.findall(r"\d+", p_val)]
            if len(digits) == 1:
                auto_tags.append(f"{digits[0]}PL")
            elif len(digits) >= 2:
                auto_tags.append(f"{digits[0]}〜{digits[1]}PL")

    d_val = value("duration")
    if isinstance(d_val, dict):
        min_h, max_h = d_val.get("min_hours"), d_val.get("max_hours")
        if min_h is not None and max_h is not None:
            fields["duration_text"] = f"{min_h}〜{max_h}時間" if min_h != max_h else f"{min_h}時間"
    elif isinstance(d_val, str):
        fields["duration_text"] = d_val[:50]

    if value("overview"):
        fields["overview"] = str(value("overview"))[:10000]
    if value("synopsis"):
        fields["synopsis"] = str(value("synopsis"))[:10000]
    return fields, auto_tags


def to_hiragana(text):
    s = unicodedata.normalize("NFKC", text or "")
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in s)


def auto_reading(title):
    t = unicodedata.normalize("NFKC", title or "").strip()
    if not t:
        return None
    for c in t:
        if not ("\u3041" <= c <= "\u3096" or "\u30a1" <= c <= "\u30fa" or c in "ー・  " or c.isascii()):
            return None
    return to_hiragana(t)[:200]


def reading_key(text):
    s = to_hiragana(text).lower()
    s = s.lstrip("「『【［〔（(<《〈\"'・  ")
    base = "".join(c for c in unicodedata.normalize("NFD", s) if c not in "\u3099\u309a")
    return (base, s)


def first_number(text):
    m = re.search(r"\d+", unicodedata.normalize("NFKC", str(text or "")[:100]))
    return int(m.group()) if m else None


EXCLUDED_AUTO_TAGS = {"trpg"}


def is_excluded_tag(name):
    return unicodedata.normalize("NFKC", name or "").strip().lower() in EXCLUDED_AUTO_TAGS


def _is_murder_mystery(name):
    n = unicodedata.normalize("NFKC", name or "").lower().replace(" ", "")
    return n in ("マダミス", "マーダーミステリー", "murdermystery")


def canonical_tag(name):
    raw = (name or "").strip()[:50]
    n = unicodedata.normalize("NFKC", raw).lower().replace(" ", "")
    if "クトゥルフ" in n or "cthulhu" in n or re.fullmatch(r"coc\d*(版|th|rd|ed)?", n):
        return "CoC"
    if _is_murder_mystery(raw):
        return "マダミス"
    return raw


def canonical_system(name):
    if name is None:
        return None
    raw = str(name).strip()[:100]
    if _is_murder_mystery(raw):
        return "マーダーミステリー"
    return raw or None


SORT_OPTIONS = [
    ("登録が新しい順", "added_desc"),
    ("登録が古い順", "added_asc"),
    ("題名順（あ→ん）", "title_asc"),
    ("題名順（ん→あ）", "title_desc"),
    ("システム順", "system"),
    ("PL人数が少ない順", "players"),
    ("所要時間が短い順", "duration"),
    ("最近開いた順", "opened"),
]


def sort_items(items, key):
    def title_key(it):
        row, kana = it[0], it[1]
        return reading_key(kana or row[2] or "")

    def missing_last(v):
        return (v is None, v if v is not None else 0)

    if key == "added_asc":
        return sorted(items, key=lambda it: it[0][0])
    if key == "title_asc":
        return sorted(items, key=title_key)
    if key == "title_desc":
        return sorted(items, key=title_key, reverse=True)
    if key == "system":
        return sorted(items, key=lambda it: ((it[0][3] or "") == "", reading_key(it[0][3] or ""), title_key(it)))
    if key == "players":
        return sorted(items, key=lambda it: (missing_last(first_number(it[0][4])), title_key(it)))
    if key == "duration":
        return sorted(items, key=lambda it: (missing_last(first_number(it[0][5])), title_key(it)))
    if key == "opened":
        return sorted(items, key=lambda it: (it[2] or "", it[0][0]), reverse=True)
    return sorted(items, key=lambda it: it[0][0], reverse=True)


def open_containing_folder(path):
    if not path or not str(path).strip():
        return
    norm_path = os.path.normpath(str(path).strip())
    if norm_path in (".", "..") or not os.path.isabs(norm_path):
        return
    folder = norm_path if os.path.isdir(norm_path) else os.path.dirname(norm_path)
    if not os.path.isdir(folder):
        messagebox.showerror("エラー", f"フォルダが見つかりません:\n{folder}")
        return
    try:
        if hasattr(os, "startfile"):
            os.startfile(folder)
        else:
            webbrowser.open("file://" + folder)
    except Exception as e:
        messagebox.showerror("エラー", f"フォルダを開けませんでした:\n{e}")


def make_link_label(parent, text, command, **pack_opts):
    lbl = tk.Label(parent, text=text, fg=C.LINK, background=C.SURFACE, cursor="hand2", font=FONT_LINK, anchor="w", justify="left")
    lbl.bind("<Button-1>", lambda e: command())
    lbl.pack(**({"anchor": "w"} | pack_opts))
    return lbl


# ==============================================================================
# 2. データベース層 (SQLite)
# ==============================================================================
class Database:
    def __init__(self, db_path=DB_PATH):
        self.conn = sqlite3.connect(db_path, timeout=10.0)
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self.init_db()

    def init_db(self):
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    system_name TEXT,
                    players_text TEXT,
                    duration_text TEXT,
                    overview TEXT,
                    synopsis TEXT,
                    thumbnail BLOB,
                    is_last_opened INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            for col in ["overview", "synopsis", "source_url", "title_kana", "last_opened_at", "notion_page_id", "notion_cover_hash",
                        "author", "play_status"]:
                try:
                    self.conn.execute(f"ALTER TABLE items ADD COLUMN {col} TEXT;")
                except sqlite3.OperationalError:
                    pass
            try:
                self.conn.execute("ALTER TABLE items ADD COLUMN favorite INTEGER DEFAULT 0;")
            except sqlite3.OperationalError:
                pass

            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL
                );
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS item_tags (
                    item_id INTEGER,
                    tag_id INTEGER,
                    PRIMARY KEY (item_id, tag_id),
                    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE,
                    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
                );
            """)

    def save_item(self, file_path, title, system_name, players_text, duration_text, overview, synopsis, thumbnail_bytes):
        system_name = canonical_system(system_name)
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO items (file_path, title, system_name, players_text, duration_text, overview, synopsis, thumbnail)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(file_path) DO UPDATE SET
                    title = excluded.title,
                    system_name = excluded.system_name,
                    players_text = excluded.players_text,
                    duration_text = excluded.duration_text,
                    overview = excluded.overview,
                    synopsis = excluded.synopsis,
                    thumbnail = excluded.thumbnail;
            """, (file_path, title, system_name, players_text, duration_text, overview, synopsis, thumbnail_bytes))
            cursor.execute("SELECT id FROM items WHERE file_path = ?;", (file_path,))
            return cursor.fetchone()[0]

    def update_item_cover(self, item_id, thumbnail_bytes):
        with self.conn:
            self.conn.execute("UPDATE items SET thumbnail = ? WHERE id = ?;", (thumbnail_bytes, item_id))

    def delete_item(self, item_id):
        """指定したシナリオアイテムおよび関連タグをデータベースから安全に削除する"""
        with self.conn:
            self.conn.execute("DELETE FROM item_tags WHERE item_id = ?;", (item_id,))
            self.conn.execute("DELETE FROM items WHERE id = ?;", (item_id,))

    def update_item_meta(self, item_id, title, system_name, players_text, duration_text, title_kana=None, author=None):
        system_name = canonical_system(system_name)
        with self.conn:
            self.conn.execute("""
                UPDATE items SET
                    title = ?,
                    title_kana = ?,
                    system_name = ?,
                    players_text = ?,
                    duration_text = ?,
                    author = ?
                WHERE id = ?;
            """, (title, title_kana, system_name, players_text, duration_text, author, item_id))

    def get_author(self, item_id):
        cursor = self.conn.cursor()
        cursor.execute("SELECT author FROM items WHERE id = ?;", (item_id,))
        row = cursor.fetchone()
        return row[0] if row else None

    def set_favorite(self, item_id, on):
        with self.conn:
            self.conn.execute("UPDATE items SET favorite = ? WHERE id = ?;", (1 if on else 0, item_id))

    def set_play_status(self, item_id, status):
        with self.conn:
            self.conn.execute("UPDATE items SET play_status = ? WHERE id = ?;", (status or None, item_id))

    def all_records(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, file_path, title, title_kana, system_name, players_text, duration_text, overview, synopsis,
                   thumbnail, author, favorite, play_status, last_opened_at
            FROM items ORDER BY id DESC;
        """)
        cols = [d[0] for d in cursor.description]
        rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
        cursor.execute("""
            SELECT it.item_id, t.id, t.name FROM item_tags it JOIN tags t ON t.id = it.tag_id ORDER BY t.name;
        """)
        tags = {}
        for item_id, tid, name in cursor.fetchall():
            tags.setdefault(item_id, []).append((tid, name))
        for r in rows:
            r["tags"] = tags.get(r["id"], [])
            r["favorite"] = bool(r["favorite"])
            r["play_status"] = r["play_status"] or ""
        return rows

    def get_title_kana(self, item_id):
        cursor = self.conn.cursor()
        cursor.execute("SELECT title_kana FROM items WHERE id = ?;", (item_id,))
        row = cursor.fetchone()
        return row[0] if row else None

    def set_title_kana(self, item_id, kana):
        with self.conn:
            self.conn.execute("UPDATE items SET title_kana = ? WHERE id = ?;", (kana or None, item_id))

    def pop_legacy_settings(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'settings';")
        if not cursor.fetchone():
            return {}
        cursor.execute("SELECT key, value FROM settings;")
        values = dict(cursor.fetchall())
        with self.conn:
            self.conn.execute("DROP TABLE settings;")
        return values

    def items_for_notion(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, file_path, title, title_kana, author, system_name, players_text, duration_text, overview, synopsis,
                   source_url, thumbnail, notion_page_id, notion_cover_hash
            FROM items ORDER BY id;
        """)
        cols = [d[0] for d in cursor.description]
        rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
        for r in rows:
            r["tags"] = [t[1] for t in self.get_item_tags(r["id"])]
        return rows

    def set_notion_link(self, item_id, page_id, cover_hash=None):
        with self.conn:
            if cover_hash is None:
                self.conn.execute("UPDATE items SET notion_page_id = ? WHERE id = ?;", (page_id, item_id))
            else:
                self.conn.execute(
                    "UPDATE items SET notion_page_id = ?, notion_cover_hash = ? WHERE id = ?;", (page_id, cover_hash, item_id)
                )

    def get_source_url(self, item_id):
        cursor = self.conn.cursor()
        cursor.execute("SELECT source_url FROM items WHERE id = ?;", (item_id,))
        row = cursor.fetchone()
        return row[0] if row else None

    def set_source_url(self, item_id, url):
        with self.conn:
            self.conn.execute("UPDATE items SET source_url = ? WHERE id = ?;", (url or None, item_id))

    def update_item_fields(self, item_id, fields):
        allowed = {"title", "system_name", "players_text", "duration_text", "overview", "synopsis", "thumbnail", "source_url", "author"}
        cols = [c for c in fields if c in allowed]
        if not cols:
            return
        if "system_name" in fields:
            fields = {**fields, "system_name": canonical_system(fields["system_name"])}
        with self.conn:
            self.conn.execute(
                f"UPDATE items SET {', '.join(f'{c} = ?' for c in cols)} WHERE id = ?;",
                (*[fields[c] for c in cols], item_id),
            )

    def add_tags_to_item(self, item_id, names):
        current = [t[0] for t in self.get_item_tags(item_id)]
        for name in names:
            tid = self.add_tag(name)
            if tid and tid not in current:
                current.append(tid)
        self.set_item_tags(item_id, current)

    def update_item_texts(self, item_id, overview, synopsis):
        with self.conn:
            self.conn.execute("UPDATE items SET overview = ?, synopsis = ? WHERE id = ?;", (overview, synopsis, item_id))

    def get_item(self, item_id):
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, file_path, title, system_name, players_text, duration_text, overview, synopsis, thumbnail
            FROM items WHERE id = ?;
        """, (item_id,))
        return cursor.fetchone()

    def set_last_opened(self, item_id):
        with self.conn:
            self.conn.execute("UPDATE items SET is_last_opened = 0;")
            self.conn.execute(
                "UPDATE items SET is_last_opened = 1, last_opened_at = strftime('%Y-%m-%d %H:%M:%f', 'now') WHERE id = ?;",
                (item_id,),
            )

    def get_last_opened(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, file_path, title FROM items WHERE is_last_opened = 1 LIMIT 1;")
        return cursor.fetchone()

    def get_tags(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, name FROM tags ORDER BY name ASC;")
        return cursor.fetchall()

    def add_tag(self, name):
        name = canonical_tag(name)
        if not name:
            return None
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO tags (name) VALUES (?);", (name,))
            cursor.execute("SELECT id FROM tags WHERE name = ?;", (name,))
            row = cursor.fetchone()
            return row[0] if row else None

    def delete_tag(self, tag_id):
        with self.conn:
            self.conn.execute("DELETE FROM tags WHERE id = ?;", (tag_id,))

    def get_tag_by_name(self, name):
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, name FROM tags WHERE name = ?;", (str(name).strip(),))
        return cursor.fetchone()

    def rename_tag(self, tag_id, new_name):
        new_name = canonical_tag(new_name)
        if not new_name:
            return None
        existing = self.get_tag_by_name(new_name)
        with self.conn:
            if existing and existing[0] != tag_id:
                self.conn.execute(
                    "INSERT OR IGNORE INTO item_tags (item_id, tag_id) SELECT item_id, ? FROM item_tags WHERE tag_id = ?;",
                    (existing[0], tag_id),
                )
                self.conn.execute("DELETE FROM tags WHERE id = ?;", (tag_id,))
                return existing[0]
            self.conn.execute("UPDATE tags SET name = ? WHERE id = ?;", (new_name, tag_id))
            return tag_id

    def normalize_tags(self):
        for tid, name in self.get_tags():
            canonical = canonical_tag(name)
            if canonical != name:
                self.rename_tag(tid, canonical)
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, system_name FROM items WHERE system_name IS NOT NULL;")
        with self.conn:
            for item_id, system_name in cursor.fetchall():
                canonical = canonical_system(system_name)
                if canonical != system_name:
                    self.conn.execute("UPDATE items SET system_name = ? WHERE id = ?;", (canonical, item_id))

    def get_tag_usage(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT tag_id, COUNT(*) FROM item_tags GROUP BY tag_id;")
        return dict(cursor.fetchall())

    def get_item_tags(self, item_id):
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT t.id, t.name FROM tags t
            JOIN item_tags it ON t.id = it.tag_id
            WHERE it.item_id = ?
            ORDER BY t.name ASC;
        """, (item_id,))
        return cursor.fetchall()

    def set_item_tags(self, item_id, tag_ids):
        valid_ids = [tid for tid in tag_ids if isinstance(tid, int)]
        with self.conn:
            self.conn.execute("DELETE FROM item_tags WHERE item_id = ?;", (item_id,))
            for tid in valid_ids:
                self.conn.execute("INSERT INTO item_tags (item_id, tag_id) VALUES (?, ?);", (item_id, tid))

    def toggle_item_tag(self, item_id, tag_name, enabled=None):
        """指定したタグの付与/解除を切り替える（enabled が指定されていればその状態に設定）"""
        current_tags = {t[1]: t[0] for t in self.get_item_tags(item_id)}
        tid = self.add_tag(tag_name)
        if not tid:
            return False
        with self.conn:
            has_tag = tag_name in current_tags
            new_state = (not has_tag) if enabled is None else bool(enabled)
            if new_state and not has_tag:
                self.conn.execute("INSERT OR IGNORE INTO item_tags (item_id, tag_id) VALUES (?, ?);", (item_id, tid))
            elif not new_state and has_tag:
                self.conn.execute("DELETE FROM item_tags WHERE item_id = ? AND tag_id = ?;", (item_id, tid))
            return new_state


# ==============================================================================
# 3. ダイアログ・詳細UI
# ==============================================================================
def make_fleur_image(size=18, color=C.ACCENT_TEXT):
    """西洋アンティーク調のフルール・ド・リス（百合紋章）アイコンを生成"""
    k = 4
    S = size * k
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx, cy = S / 2, S / 2

    # 中央の花弁
    pts_center = [
        (cx, cy - S * 0.44),
        (cx + S * 0.12, cy - S * 0.10),
        (cx + S * 0.08, cy + S * 0.15),
        (cx, cy + S * 0.10),
        (cx - S * 0.08, cy + S * 0.15),
        (cx - S * 0.12, cy - S * 0.10),
    ]
    d.polygon(pts_center, fill=color)

    # 左の花弁
    pts_left = [
        (cx - S * 0.06, cy + S * 0.05),
        (cx - S * 0.28, cy - S * 0.15),
        (cx - S * 0.40, cy - S * 0.02),
        (cx - S * 0.28, cy + S * 0.20),
        (cx - S * 0.06, cy + S * 0.14),
    ]
    d.polygon(pts_left, fill=color)

    # 右の花弁
    pts_right = [
        (cx + S * 0.06, cy + S * 0.05),
        (cx + S * 0.28, cy - S * 0.15),
        (cx + S * 0.40, cy - S * 0.02),
        (cx + S * 0.28, cy + S * 0.20),
        (cx + S * 0.06, cy + S * 0.14),
    ]
    d.polygon(pts_right, fill=color)

    # 根元の結束飾り
    pts_base = [
        (cx - S * 0.16, cy + S * 0.14),
        (cx + S * 0.16, cy + S * 0.14),
        (cx + S * 0.08, cy + S * 0.36),
        (cx, cy + S * 0.44),
        (cx - S * 0.08, cy + S * 0.36),
    ]
    d.polygon(pts_base, fill=color)

    return ImageTk.PhotoImage(im.resize((size, size), Image.LANCZOS))


def make_mini_fleur_image(width=22, height=14, color=C.ACCENT_TEXT):
    """区切り線の中央に配置する小型のフルール装飾アイコンを生成"""
    k = 4
    W, H = width * k, height * k
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx, cy = W / 2, H / 2
    d.polygon([(cx, 2), (cx + 8, cy), (cx, H - 2), (cx - 8, cy)], fill=color)
    d.polygon([(cx - 14, cy), (cx, cy - 6), (cx - 6, cy + 4)], fill=color)
    d.polygon([(cx + 14, cy), (cx, cy - 6), (cx + 6, cy + 4)], fill=color)
    return ImageTk.PhotoImage(im.resize((width, height), Image.LANCZOS))


class OrnateFrame(tk.Canvas):
    """西洋アンティーク調の装飾段差枠を描画するCanvasコンテナ"""
    def __init__(self, parent, bg_color=C.BG, border_color=C.BORDER_STRONG, accent_color=C.ACCENT):
        super().__init__(parent, background=bg_color, highlightthickness=0)
        self.bg_color = bg_color
        self.border_color = border_color
        self.accent_color = accent_color
        self.bind("<Configure>", self._draw_ornaments)

    def _draw_ornaments(self, event=None):
        self.delete("ornament")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 60 or h < 60:
            return

        x1, y1 = 12, 12
        x2, y2 = w - 12, h - 12
        s = 14  # 段差サイズ

        # 隅が切り欠かれた主枠線
        pts = [
            x1 + s, y1 + s,
            x1 + s, y1,
            x2 - s, y1,
            x2 - s, y1 + s,
            x2, y1 + s,
            x2, y2 - s,
            x2 - s, y2 - s,
            x2 - s, y2,
            x1 + s, y2,
            x1 + s, y2 - s,
            x1, y2 - s,
            x1, y1 + s,
            x1 + s, y1 + s,
        ]
        self.create_line(*pts, fill=self.border_color, width=1, tags="ornament")

        # 4隅の外側飾りブラケットと斜め装飾
        # 左上
        self.create_line(x1 + 3, y1 + s - 3, x1 + 3, y1 + 3, x1 + s - 3, y1 + 3, fill=self.accent_color, width=1, tags="ornament")
        self.create_line(x1 + 5, y1 + s - 1, x1 + s - 1, y1 + 5, fill=self.accent_color, width=1, tags="ornament")
        # 右上
        self.create_line(x2 - 3, y1 + s - 3, x2 - 3, y1 + 3, x2 - s + 3, y1 + 3, fill=self.accent_color, width=1, tags="ornament")
        self.create_line(x2 - 5, y1 + s - 1, x2 - s + 1, y1 + 5, fill=self.accent_color, width=1, tags="ornament")
        # 左下
        self.create_line(x1 + 3, y2 - s + 3, x1 + 3, y2 - 3, x1 + s - 3, y2 - 3, fill=self.accent_color, width=1, tags="ornament")
        self.create_line(x1 + 5, y2 - s + 1, x1 + s - 1, y2 - 5, fill=self.accent_color, width=1, tags="ornament")
        # 右下
        self.create_line(x2 - 3, y2 - s + 3, x2 - 3, y2 - 3, x2 - s + 3, y2 - 3, fill=self.accent_color, width=1, tags="ornament")
        self.create_line(x2 - 5, y2 - s + 1, x2 - s + 1, y2 - 5, fill=self.accent_color, width=1, tags="ornament")


class ItemDetailDialog(tk.Toplevel):
    """
    シナリオ表紙・アイコンをクリックした際に表示される詳細プレビュー・編集ウィンドウ。
    西洋古書・グリモワール調のデザインで閲覧でき、右下の「✎ 編集」から全項目を編集可能です。
    """
    def __init__(self, parent, db, item_id, on_update_callback=None, extractor=None, focus_url=False):
        super().__init__(parent)
        self.title("異編-紙票-あらすじ編集")
        self.transient(parent)
        self.grab_set()
        self.configure(background=C.BG)
        self._is_detail_dialog = True

        # ウィンドウ位置: INIファイルに保存値があれば復元、初期値は親ウィンドウの中央
        saved_geom = get_saved_geometry("detail", 980, 860)
        if saved_geom:
            self.geometry(saved_geom)
        else:
            center_on_parent(self, parent, 980, 860)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._geom_save_job = None
        self.bind("<Configure>", self._on_configure, add="+")
        apply_window_titlebar_theme(self, borderless=True)

        self.db = db
        self.item_id = item_id
        self.on_update_callback = on_update_callback
        self.extractor = extractor
        self.photo = None
        self.fetching = False
        self.file_path = ""
        self.is_edit_mode = False

        self.fleur_img = make_fleur_image(20, C.ACCENT_TEXT)
        self.mini_fleur_img = make_mini_fleur_image(20, 12, C.ACCENT_TEXT)

        # 1. カスタムタイトルバー
        self.titlebar = CustomTitleBar(self, self, title_text="異編-紙票-あらすじ編集", is_dialog=True, geom_key="detail")

        # 2. UI構築
        self.setup_ui()
        self.load_data()

        if focus_url:
            self.switch_to_edit_mode()
            self.edit_url.focus_set()

    def _on_configure(self, event):
        if event.widget == self:
            if getattr(self, "_is_window_dragging", False):
                return
            if self._geom_save_job:
                self.after_cancel(self._geom_save_job)
            self._geom_save_job = self.after(500, self._auto_save_geometry)

    def _auto_save_geometry(self):
        self._geom_save_job = None
        save_geometry("detail", self)

    def _on_close(self):
        if self._geom_save_job:
            self.after_cancel(self._geom_save_job)
        save_geometry("detail", self)
        self.destroy()

    def setup_ui(self):
        body = tk.Frame(self, background=C.BG, padx=16, pady=8)
        body.pack(fill=tk.BOTH, expand=True)

        # ----------------------------------------------------------------------
        # 左カラム: 表紙画像 & タグ
        # ----------------------------------------------------------------------
        left_col = tk.Frame(body, background=C.BG, width=260)
        left_col.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 16))
        left_col.pack_propagate(False)

        # 1. 表紙画像セクション
        tk.Label(
            left_col, text="表紙画像", font=FONT_SMALL_BOLD,
            foreground=C.TEXT, background=C.BG
        ).pack(anchor="w", pady=(0, 6))

        box_cover = tk.Frame(
            left_col, background=C.SURFACE,
            highlightthickness=1, highlightbackground=C.BORDER_STRONG,
            padx=8, pady=8
        )
        box_cover.pack(fill=tk.X, pady=(0, 14))

        self.lbl_cover = tk.Label(box_cover, background="#050505", text="[表紙なし]", foreground=C.MUTED)
        self.lbl_cover.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        self.btn_change_cover = tk.Label(
            box_cover, text="表紙を変更 (画像選択)", font=FONT_SMALL,
            foreground=C.TEXT, background=C.SURFACE,
            highlightthickness=1, highlightbackground=C.BORDER,
            padx=10, pady=6, cursor="hand2"
        )
        self.btn_change_cover.pack(fill=tk.X)
        self.btn_change_cover.bind("<Button-1>", lambda e: self.on_change_cover())
        self.btn_change_cover.bind("<Enter>", lambda e: self.btn_change_cover.configure(background=C.HOVER, highlightbackground=C.ACCENT))
        self.btn_change_cover.bind("<Leave>", lambda e: self.btn_change_cover.configure(background=C.SURFACE, highlightbackground=C.BORDER))

        # 2. タグセクション
        tk.Label(
            left_col, text="タグ", font=FONT_SMALL_BOLD,
            foreground=C.TEXT, background=C.BG
        ).pack(anchor="w", pady=(0, 6))

        box_tag = tk.Frame(
            left_col, background=C.SURFACE,
            highlightthickness=1, highlightbackground=C.BORDER_STRONG,
            padx=8, pady=8
        )
        box_tag.pack(fill=tk.X)

        self.lbl_tags = tk.Label(
            box_tag, text="なし", font=FONT_SMALL,
            foreground=C.TEXT, background=C.SURFACE,
            wraplength=230, justify="left", anchor="w"
        )
        self.lbl_tags.pack(fill=tk.X, pady=(2, 10))

        self.btn_edit_tags = tk.Label(
            box_tag, text="タグを編集", font=FONT_SMALL,
            foreground=C.TEXT, background=C.SURFACE,
            highlightthickness=1, highlightbackground=C.BORDER,
            padx=10, pady=6, cursor="hand2"
        )
        self.btn_edit_tags.pack(fill=tk.X)
        self.btn_edit_tags.bind("<Button-1>", lambda e: self.on_edit_tags())
        self.btn_edit_tags.bind("<Enter>", lambda e: self.btn_edit_tags.configure(background=C.HOVER, highlightbackground=C.ACCENT))
        self.btn_edit_tags.bind("<Leave>", lambda e: self.btn_edit_tags.configure(background=C.SURFACE, highlightbackground=C.BORDER))

        # ----------------------------------------------------------------------
        # 右カラム: 西洋古書装飾フレーム (OrnateFrame) & スクロール可能領域
        # ----------------------------------------------------------------------
        self.right_frame = OrnateFrame(body, bg_color=C.BG, border_color=C.BORDER_STRONG, accent_color=C.ACCENT)
        self.right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # 内部スクロール用Canvas
        self.scroll_canvas = tk.Canvas(self.right_frame, background=C.BG, highlightthickness=0)
        self.scroll_canvas.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)

        self.content_frame = tk.Frame(self.scroll_canvas, background=C.BG, padx=16, pady=8)
        self.inner_win_id = self.scroll_canvas.create_window((0, 0), window=self.content_frame, anchor="nw")

        self.scroll_canvas.bind("<Configure>", self._on_scroll_resize)
        self.content_frame.bind("<Configure>", lambda e: self._update_scroll_region())

        # マウスホイールによるスクロール
        self.scroll_canvas.bind_all("<MouseWheel>", self._on_mousewheel, add="+")
        self.scroll_canvas.bind_all("<Button-4>", lambda e: self._on_mousewheel(e, up=True), add="+")
        self.scroll_canvas.bind_all("<Button-5>", lambda e: self._on_mousewheel(e, up=False), add="+")

        # 閲覧モードコンテナ
        self.view_container = tk.Frame(self.content_frame, background=C.BG)
        self.view_container.pack(fill=tk.BOTH, expand=True)

        # 編集モードコンテナ
        self.edit_container = tk.Frame(self.content_frame, background=C.BG)

        self._build_view_ui(self.view_container)
        self._build_edit_ui(self.edit_container)

    def _on_scroll_resize(self, event=None):
        cw = max(100, self.scroll_canvas.winfo_width())
        self.scroll_canvas.itemconfigure(self.inner_win_id, width=cw)
        self._update_scroll_region()

    def _update_scroll_region(self):
        self.scroll_canvas.configure(scrollregion=self.scroll_canvas.bbox("all"))

    def _on_mousewheel(self, event, up=None):
        if not self.winfo_exists():
            return
        # ダイアログ上にカーソルがある場合のみスクロール
        x, y = self.winfo_pointerxy()
        wx, wy = self.scroll_canvas.winfo_rootx(), self.scroll_canvas.winfo_rooty()
        ww, wh = self.scroll_canvas.winfo_width(), self.scroll_canvas.winfo_height()
        if not (wx <= x <= wx + ww and wy <= y <= wy + wh):
            return

        if up is None:
            delta = -1 if event.delta > 0 else 1
        else:
            delta = -1 if up else 1
        self.scroll_canvas.yview_scroll(delta * 2, "units")

    def _create_section_header(self, parent, title, has_mini_fleur=False):
        f = tk.Frame(parent, background=C.BG)
        f.pack(fill=tk.X, pady=(14, 8))

        lbl_fleur = tk.Label(f, image=self.fleur_img, background=C.BG)
        lbl_fleur.pack(side=tk.LEFT, padx=(0, 8))

        lbl_title = tk.Label(f, text=title, font=FONT_HEADING, foreground=C.TEXT, background=C.BG)
        lbl_title.pack(side=tk.LEFT, padx=(0, 12))

        canv = tk.Canvas(f, background=C.BG, height=16, highlightthickness=0)
        canv.pack(side=tk.LEFT, fill=tk.X, expand=True)

        if has_mini_fleur:
            def draw_line(e=None):
                canv.delete("all")
                cw = canv.winfo_width()
                mid = cw / 2
                canv.create_line(0, 8, max(0, mid - 16), 8, fill=C.BORDER_STRONG, width=1)
                canv.create_image(mid, 8, image=self.mini_fleur_img)
                canv.create_line(min(cw, mid + 16), 8, cw, 8, fill=C.BORDER_STRONG, width=1)
            canv.bind("<Configure>", draw_line)
        else:
            canv.bind("<Configure>", lambda e: (canv.delete("all"), canv.create_line(0, 8, canv.winfo_width(), 8, fill=C.BORDER_STRONG, width=1)))

    def _build_view_ui(self, parent):
        # 1. 基本情報
        self._create_section_header(parent, "基本情報", has_mini_fleur=True)

        meta_grid = tk.Frame(parent, background=C.BG)
        meta_grid.pack(fill=tk.X, padx=(28, 10), pady=(0, 6))

        rows_def = [
            ("読み仮名", "lbl_kana"),
            ("題名", "lbl_title"),
            ("作者", "lbl_author"),
            ("システム", "lbl_system"),
            ("PL人数", "lbl_players"),
            ("所要時間", "lbl_duration"),
        ]

        for r, (label_text, attr_name) in enumerate(rows_def):
            tk.Label(
                meta_grid, text=label_text, font=FONT_BOOK,
                foreground=C.TEXT, background=C.BG, width=10, anchor="w"
            ).grid(row=r, column=0, sticky="w", pady=3)

            lbl = tk.Label(
                meta_grid, text="", font=FONT_BOOK,
                foreground=C.TEXT, background=C.BG, anchor="w"
            )
            lbl.grid(row=r, column=1, sticky="w", pady=3, padx=(20, 0))
            setattr(self, attr_name, lbl)

        # ファイル・フォルダリンク
        self.lbl_path = tk.Label(
            meta_grid, text="", font=(FONT_BOOK, 9, "underline"),
            foreground=C.ACCENT_TEXT, background=C.BG, cursor="hand2"
        )
        self.lbl_path.grid(row=len(rows_def), column=0, columnspan=2, sticky="w", pady=(8, 2))
        self.lbl_path.bind("<Button-1>", lambda e: self.on_open_folder())

        # 2. 情報元のURL
        self._create_section_header(parent, "情報元のURL")

        url_frame = tk.Frame(parent, background=C.BG)
        url_frame.pack(fill=tk.X, padx=(28, 10), pady=(0, 6))

        self.lbl_url = tk.Label(
            url_frame, text="", font=("Segoe UI", 10),
            foreground=C.TEXT, background=C.BG, cursor="hand2"
        )
        self.lbl_url.pack(anchor="w")
        self.lbl_url.bind("<Button-1>", lambda e: self.on_open_url())
        self.lbl_url.bind("<Enter>", lambda e: self.lbl_url.configure(foreground=C.ACCENT_TEXT))
        self.lbl_url.bind("<Leave>", lambda e: self.lbl_url.configure(foreground=C.TEXT))

        # 3. 概要
        self._create_section_header(parent, "概要")

        ov_frame = tk.Frame(parent, background=C.BG)
        ov_frame.pack(fill=tk.X, padx=(28, 10), pady=(0, 6))

        self.lbl_overview = tk.Label(
            ov_frame, text="", font=FONT_BOOK,
            foreground=C.TEXT, background=C.BG, justify="left", anchor="w"
        )
        self.lbl_overview.pack(fill=tk.X, anchor="w")

        # 4. あらすじ
        self._create_section_header(parent, "あらすじ")

        syn_frame = tk.Frame(parent, background=C.BG)
        syn_frame.pack(fill=tk.X, padx=(28, 10), pady=(0, 6))

        self.lbl_synopsis = tk.Label(
            syn_frame, text="", font=FONT_BOOK,
            foreground=C.TEXT, background=C.BG, justify="left", anchor="w"
        )
        self.lbl_synopsis.pack(fill=tk.X, anchor="w")

        # 5. 右下編集ボタン
        btn_box = tk.Frame(parent, background=C.BG)
        btn_box.pack(fill=tk.X, pady=(20, 4))

        self.btn_edit = tk.Label(
            btn_box, text="✎  編集", font=FONT_SMALL,
            foreground=C.TEXT, background=C.SURFACE,
            highlightthickness=1, highlightbackground=C.BORDER_STRONG,
            padx=18, pady=7, cursor="hand2"
        )
        self.btn_edit.pack(side=tk.RIGHT, padx=(0, 6))
        self.btn_edit.bind("<Button-1>", lambda e: self.switch_to_edit_mode())
        self.btn_edit.bind("<Enter>", lambda e: self.btn_edit.configure(background=C.HOVER, highlightbackground=C.ACCENT))
        self.btn_edit.bind("<Leave>", lambda e: self.btn_edit.configure(background=C.SURFACE, highlightbackground=C.BORDER_STRONG))

    def _build_edit_ui(self, parent):
        # 1. 基本情報編集
        self._create_section_header(parent, "基本情報の編集")

        meta_grid = tk.Frame(parent, background=C.BG)
        meta_grid.pack(fill=tk.X, padx=(28, 10), pady=(0, 6))

        entries_def = [
            ("題名:", "edit_title"),
            ("読み仮名:", "edit_kana"),
            ("作者:", "edit_author"),
            ("システム:", "edit_system"),
            ("PL人数:", "edit_players"),
            ("所要時間:", "edit_duration"),
        ]

        for r, (label_text, attr_name) in enumerate(entries_def):
            tk.Label(
                meta_grid, text=label_text, font=FONT_SMALL,
                foreground=C.TEXT, background=C.BG, width=10, anchor="w"
            ).grid(row=r, column=0, sticky="w", pady=4)

            entry = ttk.Entry(meta_grid, width=38)
            entry.grid(row=r, column=1, sticky="w", pady=4, padx=(10, 0))
            setattr(self, attr_name, entry)

        # 2. 情報元のURL編集
        self._create_section_header(parent, "情報元のURL (Booth等)")

        url_frame = tk.Frame(parent, background=C.BG)
        url_frame.pack(fill=tk.X, padx=(28, 10), pady=(0, 6))

        self.url_var = tk.StringVar()
        self.edit_url = ttk.Entry(url_frame, textvariable=self.url_var, width=38)
        self.edit_url.pack(side=tk.LEFT, padx=(0, 8))
        self.edit_url.bind("<Return>", lambda e: self.on_fetch_url())

        self.btn_fetch = ttk.Button(url_frame, text="URLから取得", command=self.on_fetch_url)
        self.btn_fetch.pack(side=tk.LEFT, padx=(0, 6))
        if self.extractor is None or not self.extractor.has_url:
            self.btn_fetch.state(["disabled"])

        ttk.Button(url_frame, text="ブラウザで開く", command=self.on_open_url).pack(side=tk.LEFT)

        self.lbl_url_status = tk.Label(parent, text="", font=FONT_CAPTION, foreground=C.MUTED, background=C.BG)
        self.lbl_url_status.pack(anchor="w", padx=(28, 0), pady=(2, 6))

        # 3. 概要編集
        self._create_section_header(parent, "概要の編集")

        ov_frame = tk.Frame(parent, background=C.BG)
        ov_frame.pack(fill=tk.X, padx=(28, 10), pady=(0, 6))

        self.txt_overview = tk.Text(
            ov_frame, wrap=tk.WORD, height=5, font=FONT,
            background=C.SURFACE, foreground=C.TEXT, insertbackground=C.TEXT,
            highlightthickness=1, highlightbackground=C.BORDER
        )
        self.txt_overview.pack(fill=tk.BOTH, expand=True)

        # 4. あらすじ編集
        self._create_section_header(parent, "あらすじの編集")

        syn_frame = tk.Frame(parent, background=C.BG)
        syn_frame.pack(fill=tk.X, padx=(28, 10), pady=(0, 6))

        self.txt_synopsis = tk.Text(
            syn_frame, wrap=tk.WORD, height=8, font=FONT,
            background=C.SURFACE, foreground=C.TEXT, insertbackground=C.TEXT,
            highlightthickness=1, highlightbackground=C.BORDER
        )
        self.txt_synopsis.pack(fill=tk.BOTH, expand=True)

        # 5. 操作ボタン群 (保存 / 閲覧に戻る)
        act_box = tk.Frame(parent, background=C.BG)
        act_box.pack(fill=tk.X, pady=(18, 4))

        ttk.Button(act_box, text="保存", style="Accent.TButton", command=self.on_save_all).pack(side=tk.RIGHT, padx=(6, 6))
        ttk.Button(act_box, text="閲覧に戻る", command=self.switch_to_view_mode).pack(side=tk.RIGHT)

    def switch_to_edit_mode(self):
        self.is_edit_mode = True
        self.view_container.pack_forget()
        self.edit_container.pack(fill=tk.BOTH, expand=True)
        self._update_scroll_region()
        self.scroll_canvas.yview_moveto(0)

    def switch_to_view_mode(self):
        self.is_edit_mode = False
        self.edit_container.pack_forget()
        self.view_container.pack(fill=tk.BOTH, expand=True)
        self._update_scroll_region()
        self.scroll_canvas.yview_moveto(0)

    def load_data(self):
        row = self.db.get_item(self.item_id)
        if not row:
            return

        _, file_path, title, system_name, players, duration, overview, synopsis, thumb_data = row
        self.file_path = file_path or ""
        kana = self.db.get_title_kana(self.item_id) or ""
        author = self.db.get_author(self.item_id) or ""
        source_url = self.db.get_source_url(self.item_id) or ""

        # --- 閲覧UIへの反映 ---
        self.lbl_kana.config(text=kana if kana else "未設定", foreground=C.TEXT if kana else C.MUTED)
        self.lbl_title.config(text=title if title else "未設定", foreground=C.TEXT if title else C.MUTED)
        self.lbl_author.config(text=author if author else "未設定", foreground=C.TEXT if author else C.MUTED)
        self.lbl_system.config(text=system_name if system_name else "未指定", foreground=C.TEXT if system_name else C.MUTED)
        self.lbl_players.config(text=players if players else "未設定", foreground=C.TEXT if players else C.MUTED)
        self.lbl_duration.config(text=duration if duration else "未設定", foreground=C.TEXT if duration else C.MUTED)

        # ファイルパス/所在表示
        display_path = file_path if file_path else "所在不明"
        self.lbl_path.config(text=display_path)

        # URL
        if source_url:
            self.lbl_url.config(text=source_url, foreground=C.TEXT)
        else:
            self.lbl_url.config(text="未設定", foreground=C.MUTED)

        # 概要
        if overview:
            self.lbl_overview.config(text=overview, foreground=C.TEXT)
        else:
            self.lbl_overview.config(text="未設定", foreground=C.MUTED)

        # あらすじ
        if synopsis:
            self.lbl_synopsis.config(text=synopsis, foreground=C.TEXT)
        else:
            self.lbl_synopsis.config(text="未設定", foreground=C.MUTED)

        # --- 編集UIへの反映 ---
        self._set_entry(self.edit_title, title or "")
        self._set_entry(self.edit_kana, kana or "")
        self._set_entry(self.edit_author, author or "")
        self._set_entry(self.edit_system, system_name or "")
        self._set_entry(self.edit_players, players or "")
        self._set_entry(self.edit_duration, duration or "")
        if not self.fetching:
            self.url_var.set(source_url)

        self.txt_overview.delete("1.0", tk.END)
        if overview:
            self.txt_overview.insert("1.0", overview)

        self.txt_synopsis.delete("1.0", tk.END)
        if synopsis:
            self.txt_synopsis.insert("1.0", synopsis)

        # タグ
        tags = self.db.get_item_tags(self.item_id)
        self.lbl_tags.config(text="、".join(t[1] for t in tags) if tags else "なし")

        # 表紙画像
        if thumb_data:
            try:
                img = Image.open(io.BytesIO(thumb_data))
                img.thumbnail((240, 260), Image.LANCZOS)
                self.photo = ImageTk.PhotoImage(img)
                self.lbl_cover.config(image=self.photo, text="")
            except Exception:
                self.lbl_cover.config(image="", text="[画像読込エラー]")
        else:
            self.lbl_cover.config(image="", text="[表紙なし]")

        self._update_scroll_region()

    def _set_entry(self, entry, text):
        entry.delete(0, tk.END)
        entry.insert(0, text)

    def on_save_all(self):
        new_title = self.edit_title.get().strip()[:200]
        if not new_title:
            messagebox.showwarning("入力不備", "題名を入力してください。", parent=self)
            return

        kana = self.edit_kana.get().strip()[:200] or auto_reading(new_title)
        author = self.edit_author.get().strip() or None
        system_name = self.edit_system.get().strip() or None
        players = self.edit_players.get().strip() or None
        duration = self.edit_duration.get().strip() or None
        url = self.url_var.get().strip()

        new_ov = self.txt_overview.get("1.0", tk.END).strip()[:10000]
        new_syn = self.txt_synopsis.get("1.0", tk.END).strip()[:10000]

        # DB一括更新
        self.db.update_item_meta(
            self.item_id,
            new_title,
            system_name,
            players,
            duration,
            title_kana=kana or None,
            author=author,
        )
        self.db.update_item_texts(self.item_id, new_ov, new_syn)
        if url:
            self.db.set_source_url(self.item_id, url)

        self.load_data()
        if self.on_update_callback:
            self.on_update_callback()

        self.switch_to_view_mode()
        messagebox.showinfo("保存完了", "情報を更新しました。", parent=self)

    def on_open_folder(self):
        if self.file_path:
            open_containing_folder(self.file_path)

    def on_open_url(self):
        url = self.url_var.get().strip() or self.db.get_source_url(self.item_id) or ""
        if url.startswith(("http://", "https://")):
            webbrowser.open(url)

    def on_fetch_url(self):
        url = self.url_var.get().strip()
        if not url.startswith(("http://", "https://")):
            messagebox.showwarning("URL", "http:// か https:// で始まる URL を入力してください。", parent=self)
            return
        if self.fetching or self.extractor is None:
            return
        self.db.set_source_url(self.item_id, url)
        self.fetching = True
        self.btn_fetch.state(["disabled"])
        self.lbl_url_status.config(text="取得中…")
        result = {}

        def work():
            try:
                result["data"], result["jpeg"] = self.extractor.extract_url(url)
            except Exception as e:
                result["error"] = str(e)

        thread = threading.Thread(target=work, daemon=True)
        thread.start()

        def poll():
            try:
                if thread.is_alive():
                    self.after(150, poll)
                    return
                self.fetching = False
                if not self.winfo_exists():
                    return
            except tk.TclError:
                return
            self.btn_fetch.state(["!disabled"])
            if "error" in result:
                self.lbl_url_status.config(text="取得できませんでした")
                messagebox.showerror("URL からの取得", result["error"], parent=self)
                return
            data = result["data"]
            self.lbl_url_status.config(text="取得完了")
            UrlResultDialog(
                self, self.db, self.item_id, data, result.get("jpeg"),
                placeholder=self.extractor.placeholder_jpeg(), on_applied=self.on_url_applied,
            )

        self.after(150, poll)

    def on_url_applied(self):
        self.load_data()
        if self.on_update_callback:
            self.on_update_callback()

    def on_edit_tags(self):
        def done():
            self.load_data()
            if self.on_update_callback:
                self.on_update_callback()

        TagEditorDialog(self, self.db, item_id=self.item_id, on_close_callback=done)

    def on_change_cover(self):
        file_path = filedialog.askopenfilename(
            title="表紙画像を選択",
            filetypes=[("画像ファイル", "*.jpg;*.jpeg;*.png;*.webp;*.bmp"), ("すべてのファイル", "*.*")]
        )
        if not file_path:
            return
        try:
            img = Image.open(file_path)
            img.thumbnail((600, 600))
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=85)
            new_thumb_bytes = buf.getvalue()

            self.db.update_item_cover(self.item_id, new_thumb_bytes)
            self.load_data()
            if self.on_update_callback:
                self.on_update_callback()
            messagebox.showinfo("更新完了", "表紙画像を変更しました。")
        except Exception as e:
            messagebox.showerror("エラー", f"画像の変換に失敗しました:\n{e}")

    # 以前の個別編集互換メソッド
    def on_edit_meta(self):
        self.switch_to_edit_mode()

    def on_save_texts(self):
        self.on_save_all()


class UrlResultDialog(tk.Toplevel):
    FIELDS = [
        ("title", "題名"),
        ("players_text", "PL人数"),
        ("duration_text", "所要時間"),
        ("overview", "概要"),
        ("synopsis", "あらすじ"),
    ]

    def __init__(self, parent, db, item_id, data, jpeg, placeholder=None, on_applied=None):
        super().__init__(parent)
        self.title("URL から取得した内容の反映")
        self.configure(background=C.BG)
        self.geometry("880x680")
        self.minsize(760, 520)
        self.transient(parent)
        self.grab_set()

        apply_window_titlebar_theme(self, borderless=True)

        self.db = db
        self.item_id = item_id
        self.data = data
        self.jpeg = jpeg
        self.on_applied = on_applied
        self.placeholder = placeholder
        self.fields, auto_tags = parse_info(data.get("info") or {})
        system = self.fields.get("system_name")
        self.auto_tags = [t for t in auto_tags if t != system and not is_excluded_tag(t)]
        self.site_tags = self.tag_names(data.get("tags", []))
        self.title_tags = self.tag_names(data.get("title_systems", []))
        self.vars = {}
        self.photos = []
        self.candidates = [c for c in (data.get("synopsis_candidates") or []) if c.get("text")]
        self.synopsis_choice = None
        self.applied = False
        self.setup_ui()
        center_on_parent(self, parent, 880, 680)
        self.after_idle(lambda: center_on_parent(self, parent, 880, 680))
        self.after(50, lambda: center_on_parent(self, parent, 880, 680))

    def build_synopsis_choices(self, parent_frame):
        container = tk.Frame(parent_frame, background=C.SURFACE)
        container.pack(fill=tk.BOTH, expand=True)
        choice = tk.IntVar(value=0)

        card_entries = []

        def update_card_visuals():
            cur = choice.get()
            for idx, entry in enumerate(card_entries):
                is_selected = (idx == cur)
                bg_col = C.SURFACE_2
                bd_col = C.ACCENT if is_selected else C.BORDER
                entry["frame"].configure(background=bg_col, highlightbackground=bd_col)
                entry["desc"].configure(background=bg_col)
                entry["top"].configure(background=bg_col)
                entry["cnt"].configure(background=bg_col)

        for i, c in enumerate(self.candidates):
            label = c.get("label") or f"候補 {i+1}"
            text = (c.get("text") or "").strip()

            if len(self.candidates) == 1:
                # 候補が1つだけの場合
                c_frame = tk.Frame(
                    container, background=C.SURFACE_2, highlightbackground=C.BORDER_STRONG,
                    highlightthickness=1, padx=10, pady=8
                )
                c_frame.pack(fill=tk.X)
                tk.Label(
                    c_frame, text=f"【{label}】", font=FONT_CAPTION,
                    foreground=C.ACCENT, background=C.SURFACE_2, anchor="w"
                ).pack(fill=tk.X)
                tk.Label(
                    c_frame, text=self.short(text, 360), font=FONT_SMALL,
                    foreground=C.TEXT, background=C.SURFACE_2, wraplength=320, justify="left", anchor="w"
                ).pack(fill=tk.X, pady=(4, 0))
            else:
                # 候補が複数の場合：クリック可能なカード
                c_frame = tk.Frame(
                    container, background=C.SURFACE_2, highlightbackground=C.BORDER,
                    highlightthickness=1, padx=10, pady=7, cursor="hand2"
                )
                c_frame.pack(fill=tk.X, pady=(0, 6))

                top_row = tk.Frame(c_frame, background=C.SURFACE_2, cursor="hand2")
                top_row.pack(fill=tk.X)

                rb = ttk.Radiobutton(
                    top_row, text=f"【{label}】", variable=choice, value=i,
                    style="Card.TRadiobutton", cursor="hand2"
                )
                rb.pack(side=tk.LEFT)

                char_cnt = tk.Label(
                    top_row, text=f"({len(text)}文字)", font=FONT_CAPTION,
                    foreground=C.MUTED, background=C.SURFACE_2, cursor="hand2"
                )
                char_cnt.pack(side=tk.LEFT, padx=4)

                desc_lbl = tk.Label(
                    c_frame, text=self.short(text, 200), font=FONT_SMALL,
                    foreground=C.TEXT, background=C.SURFACE_2, wraplength=320, justify="left", anchor="w",
                    cursor="hand2"
                )
                desc_lbl.pack(fill=tk.X, pady=(4, 0))

                entry_dict = {
                    "frame": c_frame,
                    "top": top_row,
                    "rb": rb,
                    "cnt": char_cnt,
                    "desc": desc_lbl,
                }
                card_entries.append(entry_dict)

                def make_select_handler(idx=i):
                    def handler(e):
                        choice.set(idx)
                        if "synopsis" in self.vars:
                            self.vars["synopsis"].set(True)
                    return handler

                select_handler = make_select_handler(i)
                for w in (c_frame, top_row, char_cnt, desc_lbl):
                    w.bind("<Button-1>", select_handler)

                # ホバー処理（ホワイトアウト防止・ダークハイライト）
                def make_hover_handlers(idx=i, ed=entry_dict):
                    def on_enter(e):
                        ed["frame"].configure(background=C.HOVER, highlightbackground=C.ACCENT_HOVER)
                        ed["top"].configure(background=C.HOVER)
                        ed["cnt"].configure(background=C.HOVER)
                        ed["desc"].configure(background=C.HOVER)
                    def on_leave(e):
                        is_sel = (choice.get() == idx)
                        bg = C.SURFACE_2
                        bd = C.ACCENT if is_sel else C.BORDER
                        ed["frame"].configure(background=bg, highlightbackground=bd)
                        ed["top"].configure(background=bg)
                        ed["cnt"].configure(background=bg)
                        ed["desc"].configure(background=bg)
                    return on_enter, on_leave

                h_enter, h_leave = make_hover_handlers(i, entry_dict)
                for w in (c_frame, top_row, char_cnt, desc_lbl):
                    w.bind("<Enter>", h_enter)
                    w.bind("<Leave>", h_leave)

        choice.trace_add("write", lambda *a: (
            update_card_visuals(),
            self.vars.get("synopsis") and self.vars["synopsis"].set(True)
        ))
        update_card_visuals()
        return choice

    @staticmethod
    def tag_names(names):
        out = []
        for n in names:
            t = canonical_tag(n)
            if t and not is_excluded_tag(t) and t not in out:
                out.append(t)
        return out

    def current_values(self):
        row = self.db.get_item(self.item_id)
        _, file_path, title, system_name, players, duration, overview, synopsis, thumb = row
        return file_path, {
            "title": title, "system_name": system_name, "players_text": players, "duration_text": duration,
            "overview": overview, "synopsis": synopsis,
        }, thumb

    def setup_ui(self):
        file_path, current, thumb = self.current_values()
        default_title = os.path.splitext(os.path.basename(os.path.normpath(file_path)))[0]

        # 1. ヘッダー
        head = tk.Frame(self, background=C.BG, padx=22, pady=16)
        head.pack(fill=tk.X)

        lbl_h = tk.Label(
            head, text="🌐  URL取得データの反映確認",
            font=FONT_TITLE, foreground=C.ACCENT_TEXT, background=C.BG, anchor="w"
        )
        lbl_h.pack(fill=tk.X, pady=(0, 2))

        lbl_desc = tk.Label(
            head, text="Webページから取得した情報です。反映したい項目にチェックを付けて「反映」を押してください。",
            font=FONT_SMALL, foreground=C.MUTED, background=C.BG, anchor="w"
        )
        lbl_desc.pack(fill=tk.X)

        tk.Frame(self, background=C.BORDER, height=1).pack(fill=tk.X)

        # 2. メインスクロールエリア
        body_outer = tk.Frame(self, background=C.BG)
        body_outer.pack(fill=tk.BOTH, expand=True, padx=16, pady=8)

        canvas = tk.Canvas(body_outer, background=C.BG, highlightthickness=0, borderwidth=0)
        sb = ttk.Scrollbar(body_outer, orient=tk.VERTICAL, command=canvas.yview)
        body = tk.Frame(canvas, background=C.BG)

        body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        win = canvas.create_window((0, 0), window=body, anchor="nw")

        def _on_canvas_configure(e):
            canvas.itemconfigure(win, width=e.width)
        canvas.bind("<Configure>", _on_canvas_configure)
        canvas.configure(yscrollcommand=sb.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        # 列タイトル（見出しバー）
        th = tk.Frame(body, background=C.BG, padx=8)
        th.pack(fill=tk.X, pady=(2, 6))
        tk.Label(th, text="反映項目", font=FONT_SMALL_BOLD, foreground=C.ACCENT_TEXT, background=C.BG, width=16, anchor="w").pack(side=tk.LEFT)
        th_split = tk.Frame(th, background=C.BG)
        th_split.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        th_split.columnconfigure(0, weight=1, uniform="th")
        th_split.columnconfigure(1, weight=1, uniform="th")
        tk.Label(th_split, text="現在の登録内容", font=FONT_SMALL_BOLD, foreground=C.MUTED, background=C.BG, anchor="w").grid(row=0, column=0, sticky="w", padx=(0, 4))
        tk.Label(th_split, text="取得した内容（反映候補）", font=FONT_SMALL_BOLD, foreground=C.GLOW, background=C.BG, anchor="w").grid(row=0, column=1, sticky="w", padx=(4, 0))

        # 3. 各項目のカード
        for key, label in self.FIELDS:
            new = self.fields.get(key)
            if not new:
                continue
            old = current.get(key)
            empty = not old or (key == "title" and old == default_title)
            richer = key in ("overview", "synopsis") and bool(old) and len(str(new)) > len(str(old))
            var = tk.BooleanVar(value=(empty or richer) and new != old)
            self.vars[key] = var

            card = tk.Frame(body, background=C.SURFACE, highlightbackground=C.BORDER, highlightthickness=1, padx=12, pady=10)
            card.pack(fill=tk.X, pady=4)

            # 左側: チェックボックスと項目名
            l_box = tk.Frame(card, background=C.SURFACE, width=130)
            l_box.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
            l_box.pack_propagate(False)

            cb = ttk.Checkbutton(l_box, variable=var, style="TCheckbutton")
            cb.pack(side=tk.LEFT, padx=(0, 6))

            lbl_name = tk.Label(l_box, text=label, font=FONT_BOLD, foreground=C.ACCENT_TEXT, background=C.SURFACE, anchor="w")
            lbl_name.pack(side=tk.LEFT, fill=tk.X, expand=True)

            # 右側: 2列グリッド（現在 vs 取得）
            r_grid = tk.Frame(card, background=C.SURFACE)
            r_grid.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            r_grid.columnconfigure(0, weight=1, uniform="col")
            r_grid.columnconfigure(1, weight=1, uniform="col")

            # 現在の内容
            old_box = tk.Frame(r_grid, background=C.SURFACE_2, highlightbackground=C.BORDER, highlightthickness=1, padx=10, pady=8)
            old_box.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
            tk.Label(
                old_box, text=self.short(old) or "（未設定）",
                font=FONT_SMALL, foreground=C.MUTED, background=C.SURFACE_2,
                wraplength=310, justify="left", anchor="nw"
            ).pack(fill=tk.BOTH, expand=True)

            # 取得した内容
            if key == "synopsis" and self.candidates:
                new_box = tk.Frame(r_grid, background=C.SURFACE)
                new_box.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
                self.synopsis_choice = self.build_synopsis_choices(new_box)
            else:
                new_box = tk.Frame(r_grid, background=C.SURFACE_2, highlightbackground=C.BORDER_STRONG, highlightthickness=1, padx=10, pady=8)
                new_box.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
                tk.Label(
                    new_box, text=self.short(new),
                    font=FONT_SMALL, foreground=C.TEXT, background=C.SURFACE_2,
                    wraplength=310, justify="left", anchor="nw"
                ).pack(fill=tk.BOTH, expand=True)

        # 4. 表紙カード
        if self.jpeg:
            var = tk.BooleanVar(value=not thumb or (self.placeholder is not None and thumb == self.placeholder))
            self.vars["thumbnail"] = var

            card = tk.Frame(body, background=C.SURFACE, highlightbackground=C.BORDER, highlightthickness=1, padx=12, pady=10)
            card.pack(fill=tk.X, pady=4)

            l_box = tk.Frame(card, background=C.SURFACE, width=130)
            l_box.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
            l_box.pack_propagate(False)

            cb = ttk.Checkbutton(l_box, variable=var, style="TCheckbutton")
            cb.pack(side=tk.LEFT, padx=(0, 6))

            lbl_name = tk.Label(l_box, text="表紙画像", font=FONT_BOLD, foreground=C.ACCENT_TEXT, background=C.SURFACE, anchor="w")
            lbl_name.pack(side=tk.LEFT, fill=tk.X, expand=True)

            r_grid = tk.Frame(card, background=C.SURFACE)
            r_grid.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            r_grid.columnconfigure(0, weight=1, uniform="col")
            r_grid.columnconfigure(1, weight=1, uniform="col")

            for col_idx, (img_bytes, is_new) in enumerate([(thumb, False), (self.jpeg, True)]):
                box = tk.Frame(
                    r_grid, background=C.SURFACE_2,
                    highlightbackground=C.BORDER_STRONG if is_new else C.BORDER,
                    highlightthickness=1, padx=10, pady=8
                )
                box.grid(row=0, column=col_idx, sticky="nsew", padx=(0, 4) if col_idx == 0 else (4, 0))

                lbl_img = tk.Label(box, text="（表紙なし）", font=FONT_SMALL, foreground=C.MUTED, background=C.SURFACE_2)
                lbl_img.pack(expand=True)
                if img_bytes:
                    try:
                        img = Image.open(io.BytesIO(img_bytes))
                        img.thumbnail((110, 145))
                        photo = ImageTk.PhotoImage(img)
                        self.photos.append(photo)
                        lbl_img.config(image=photo, text="")
                    except Exception:
                        lbl_img.config(text="[画像読込エラー]")

        # 5. タグカード
        current_tags = {t[1] for t in self.db.get_item_tags(self.item_id)}
        new_title_tags = [t for t in self.title_tags if t not in current_tags]
        if new_title_tags:
            var = tk.BooleanVar(value=True)
            self.vars["title_tags"] = var

            card = tk.Frame(body, background=C.SURFACE, highlightbackground=C.BORDER, highlightthickness=1, padx=12, pady=10)
            card.pack(fill=tk.X, pady=4)

            l_box = tk.Frame(card, background=C.SURFACE, width=130)
            l_box.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
            l_box.pack_propagate(False)

            cb = ttk.Checkbutton(l_box, variable=var, style="TCheckbutton")
            cb.pack(side=tk.LEFT, padx=(0, 6))

            lbl_name = tk.Label(l_box, text="追加タグ", font=FONT_BOLD, foreground=C.ACCENT_TEXT, background=C.SURFACE, anchor="w")
            lbl_name.pack(side=tk.LEFT, fill=tk.X, expand=True)

            r_grid = tk.Frame(card, background=C.SURFACE)
            r_grid.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

            tag_box = tk.Frame(r_grid, background=C.SURFACE_2, highlightbackground=C.BORDER_STRONG, highlightthickness=1, padx=10, pady=8)
            tag_box.pack(fill=tk.BOTH, expand=True)

            for t in new_title_tags:
                tk.Label(
                    tag_box, text=f"🏷️ {t}", font=FONT_SMALL,
                    foreground=C.TAG_FG, background=C.TAG_BG, padx=8, pady=3
                ).pack(side=tk.LEFT, padx=(0, 6), pady=2)

        # 6. 下部ボタンバー
        footer = tk.Frame(self, background=C.BG)
        footer.pack(fill=tk.X, side=tk.BOTTOM)

        tk.Frame(footer, background=C.BORDER, height=1).pack(fill=tk.X)

        btn_bar = tk.Frame(footer, background=C.BG, padx=20, pady=12)
        btn_bar.pack(fill=tk.X)

        ttk.Button(
            btn_bar, text="✔ 反映する", style="Accent.TButton", command=self.apply
        ).pack(side=tk.RIGHT, padx=(8, 0))

        ttk.Button(
            btn_bar, text="キャンセル", style="Side.TButton", command=self.destroy
        ).pack(side=tk.RIGHT)

    @staticmethod
    def short(text, limit=220):
        if not text:
            return ""
        text = str(text)
        return text if len(text) <= limit else text[:limit] + "…"

    def apply(self):
        update = {k: self.fields[k] for k, _ in self.FIELDS if k in self.vars and self.vars[k].get()}
        if "synopsis" in update and self.synopsis_choice is not None and self.candidates:
            update["synopsis"] = self.candidates[self.synopsis_choice.get()]["text"]
        if "thumbnail" in self.vars and self.vars["thumbnail"].get():
            update["thumbnail"] = self.jpeg
        self.db.update_item_fields(self.item_id, update)
        if "title" in update and not self.db.get_title_kana(self.item_id):
            self.db.set_title_kana(self.item_id, auto_reading(update["title"]))
        tags = []
        if "players_text" in update:
            tags += [t for t in self.auto_tags if t.endswith("PL") or t == "GMレス"]
        if "title_tags" in self.vars and self.vars["title_tags"].get():
            tags += self.title_tags
        if tags:
            self.db.add_tags_to_item(self.item_id, sorted(set(tags)))
        self.applied = True
        if self.on_applied:
            self.on_applied()
        self.destroy()


class ChoiceSelectDialog(tk.Toplevel):
    def __init__(self, parent, choices, on_select_callback):
        super().__init__(parent)
        self.title("表紙候補の選択")
        self.configure(background=C.BG)
        self.geometry("640x520")
        self.transient(parent)
        self.grab_set()

        apply_window_titlebar_theme(self, borderless=True)

        self.choices = choices
        self.on_select_callback = on_select_callback
        self.photo_cache = []

        self.setup_ui()
        center_on_parent(self, parent, 640, 520)
        self.after_idle(lambda: center_on_parent(self, parent, 640, 520))

    def setup_ui(self):
        lbl = tk.Label(
            self, text="🖼️  検出された画像一覧です。採用する表紙をクリックしてください：",
            font=FONT_BOLD, foreground=C.ACCENT_TEXT, background=C.BG, padx=14, pady=10, anchor="w"
        )
        lbl.pack(fill=tk.X)

        main_frame = tk.Frame(self, background=C.BG)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=5)

        canvas = tk.Canvas(main_frame, background=C.BG, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=canvas.yview)
        container = tk.Frame(canvas, background=C.BG)

        container.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        win = canvas.create_window((0, 0), window=container, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        for ch in self.choices:
            row = tk.Frame(container, background=C.SURFACE, highlightbackground=C.BORDER, highlightthickness=1, padx=8, pady=8)
            row.pack(fill=tk.X, padx=4, pady=4, expand=True)

            img_bytes = ch["jpeg"]
            try:
                img = Image.open(io.BytesIO(img_bytes))
                img.thumbnail((80, 80))
                photo = ImageTk.PhotoImage(img)
                self.photo_cache.append(photo)
                ttk.Label(row, image=photo).pack(side=tk.LEFT, padx=6)
            except Exception:
                ttk.Label(row, text="[No Image]", width=10).pack(side=tk.LEFT, padx=6)

            info_f = ttk.Frame(row)
            info_f.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=6)
            ttk.Label(info_f, text=ch.get("entry_path", ""), font=FONT_SMALL_BOLD).pack(anchor="w")

            ttk.Button(row, text="この表紙を採用", style="Accent.TButton", command=lambda b=img_bytes: self.choose(b)).pack(side=tk.RIGHT, padx=5)

    def choose(self, chosen_bytes):
        self.on_select_callback(chosen_bytes)
        self.destroy()


class TagEditorDialog(tk.Toplevel):
    def __init__(self, parent, db, item_id=None, on_close_callback=None):
        super().__init__(parent)
        self.db = db
        self.item_id = item_id
        self.on_close_callback = on_close_callback
        self.check_vars = {}
        self.selected = {t[0] for t in db.get_item_tags(item_id)} if item_id else set()

        if item_id:
            row = db.get_item(item_id)
            self.title(f"タグの編集 - {row[2] if row else ''}")
        else:
            self.title("タグの管理")
        self.geometry("440x560")
        self.transient(parent)
        self.grab_set()

        self.setup_ui()
        self.refresh()

    def setup_ui(self):
        if self.item_id:
            ttk.Label(self, text="このシナリオに付けるタグにチェックを付けてください。", padding=(10, 8, 10, 0)).pack(anchor="w")

        add_frame = ttk.LabelFrame(self, text="タグを追加", padding=(0, 2, 0, 10))
        add_frame.pack(fill=tk.X, padx=10, pady=(8, 4))
        self.entry_var = tk.StringVar()
        entry = ttk.Entry(add_frame, textvariable=self.entry_var)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        entry.bind("<Return>", lambda e: self.add_tag())
        ttk.Button(add_frame, text="追加", command=self.add_tag).pack(side=tk.RIGHT)

        search_frame = ttk.Frame(self, padding=(10, 4))
        search_frame.pack(fill=tk.X)
        ttk.Label(search_frame, text="絞り込み:").pack(side=tk.LEFT)
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *a: self.refresh())
        ttk.Entry(search_frame, textvariable=self.filter_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))

        list_frame = ttk.LabelFrame(self, text="タグ一覧", padding=(0, 2, 0, 10))
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)

        self.canvas = tk.Canvas(list_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.scroll_content = ttk.Frame(self.canvas)
        self.scroll_content.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scroll_content, anchor="nw")
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.canvas_window, width=e.width))
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        btn_bar = ttk.Frame(self, padding=10)
        btn_bar.pack(fill=tk.X)
        pin_bottom_bar(btn_bar)
        if self.item_id:
            ttk.Button(btn_bar, text="保存して適用", style="Accent.TButton", command=self.apply_item_tags).pack(side=tk.RIGHT, padx=5)
            ttk.Button(btn_bar, text="キャンセル", command=self.destroy).pack(side=tk.RIGHT)
        else:
            ttk.Button(btn_bar, text="閉じる", command=self.destroy).pack(side=tk.RIGHT)

    def refresh(self):
        for widget in self.scroll_content.winfo_children():
            widget.destroy()
        self.check_vars.clear()

        usage = self.db.get_tag_usage()
        keyword = self.filter_var.get().strip().lower() if hasattr(self, "filter_var") else ""
        tags = [t for t in self.db.get_tags() if keyword in t[1].lower()]
        if not tags:
            msg = "該当するタグがありません" if keyword else "タグがありません。上の欄から追加してください。"
            ttk.Label(self.scroll_content, text=msg, foreground=C.FAINT).pack(anchor="w", pady=4)
            return

        for tid, tname in tags:
            row = ttk.Frame(self.scroll_content)
            row.pack(fill=tk.X, pady=1)
            label = f"{tname}  ({usage.get(tid, 0)})"
            if self.item_id:
                var = tk.BooleanVar(value=(tid in self.selected))
                self.check_vars[tid] = var
                ttk.Checkbutton(row, text=label, variable=var, command=lambda i=tid, v=var: self.on_toggle(i, v)).pack(
                    side=tk.LEFT, fill=tk.X, expand=True
                )
            else:
                ttk.Label(row, text=label).pack(side=tk.LEFT, fill=tk.X, expand=True)
            ttk.Button(row, text="削除", style="Danger.Small.TButton", command=lambda i=tid, n=tname: self.del_tag(i, n)).pack(side=tk.RIGHT)
            ttk.Button(row, text="名前変更", style="Small.TButton", command=lambda i=tid, n=tname: self.rename_tag(i, n)).pack(
                side=tk.RIGHT, padx=2
            )

    def on_toggle(self, tag_id, var):
        if var.get():
            self.selected.add(tag_id)
        else:
            self.selected.discard(tag_id)

    def _notify(self):
        if self.on_close_callback:
            self.on_close_callback()

    def add_tag(self):
        val = self.entry_var.get().strip()
        if not val:
            return
        tid = self.db.add_tag(val)
        self.entry_var.set("")
        if self.item_id and tid:
            self.selected.add(tid)
        self.refresh()
        if not self.item_id:
            self._notify()

    def rename_tag(self, tag_id, old_name):
        new_name = simpledialog.askstring("タグの名前変更", "新しい名前:", initialvalue=old_name, parent=self)
        if new_name is None:
            return
        new_name = new_name.strip()
        if not new_name or new_name == old_name:
            return
        result_id = self.db.rename_tag(tag_id, new_name)
        if result_id and tag_id in self.selected and result_id != tag_id:
            self.selected.discard(tag_id)
            self.selected.add(result_id)
        self.refresh()
        self._notify()

    def del_tag(self, tag_id, name):
        count = self.db.get_tag_usage().get(tag_id, 0)
        note = f"\n（{count}件のシナリオから外れます）" if count else ""
        if messagebox.askyesno("削除確認", f"タグ「{name}」を削除しますか？{note}", parent=self):
            self.db.delete_tag(tag_id)
            self.selected.discard(tag_id)
            self.refresh()
            self._notify()

    def apply_item_tags(self):
        if self.item_id:
            valid = {t[0] for t in self.db.get_tags()}
            self.db.set_item_tags(self.item_id, sorted(self.selected & valid))
            self._notify()
        self.destroy()


# ==============================================================================
# 5. Notion 連携UI
# ==============================================================================
APP_SETTINGS = None


def load_app_settings(db=None):
    global APP_SETTINGS
    APP_SETTINGS = app_settings.Settings(os.path.join(_app_dir(), app_settings.SETTINGS_FILE))
    if db is not None:
        old = db.pop_legacy_settings()
        if old:
            s = APP_SETTINGS
            for key, (section, name) in {
                "sort": ("display", "sort"), "view": ("display", "view"),
                "notion_database_url": ("notion", "database_url"),
                "notion_data_source_id": ("notion", "data_source_id"),
                "notion_mapping": ("notion", "mapping"),
                "notion_schema": ("notion", "schema")
            }.items():
                if old.get(key) and s.get(section, name) is None:
                    s.set(section, name, old[key], save=False)
            if old.get("notion_token") and s.get("notion", "token") is None:
                s.set_secret("notion", "token", old["notion_token"], save=False)
            s.save()
    return APP_SETTINGS


def settings_store():
    return APP_SETTINGS if APP_SETTINGS is not None else load_app_settings()


def notion_settings(_db=None):
    s = settings_store()
    token = s.get_secret("notion", "token")
    return {
        "token": token or os.environ.get("NOTION_TOKEN", ""),
        "token_unreadable": token is None,
        "database_url": s.get("notion", "database_url", ""),
        "data_source_id": s.get("notion", "data_source_id", ""),
        "mapping": s.get_json("notion", "mapping", {}),
        "schema": s.get_json("notion", "schema", {}),
        "api_base": os.environ.get("NOTION_API_BASE") or None,
    }


def run_in_thread(widget, work, done, progress_label=None, state=None):
    box = {}

    def target():
        try:
            box["result"] = work()
        except Exception as e:
            box["error"] = e

    thread = threading.Thread(target=target, daemon=True)
    thread.start()

    def poll():
        try:
            if progress_label is not None and state is not None and progress_label.winfo_exists():
                progress_label.config(text=state.get("message", ""))
            if thread.is_alive():
                widget.after(150, poll)
                return
            done(box.get("result"), box.get("error"))
        except tk.TclError:
            pass

    widget.after(150, poll)


class NotionSettingsDialog(tk.Toplevel):
    def __init__(self, parent, db):
        super().__init__(parent)
        self.title("Notion 連携の設定")
        self.geometry("680x760")
        self.transient(parent)
        self.grab_set()
        self.db = db
        self.settings = notion_settings(db)
        self.schema = dict(self.settings["schema"])
        self.sources = []
        self.map_vars = {}
        self.setup_ui()
        if self.schema:
            self.build_mapping(self.settings["mapping"])

    def setup_ui(self):
        f = ttk.Frame(self, padding=(20, 16, 20, 8))
        f.pack(fill=tk.BOTH, expand=True)

        grid = ttk.Frame(f)
        grid.pack(fill=tk.X)
        ttk.Label(grid, text="トークン:").grid(row=0, column=0, sticky="w", pady=3)
        self.token_var = tk.StringVar(value=self.settings["token"])
        ttk.Entry(grid, textvariable=self.token_var, show="•", width=56).grid(row=0, column=1, sticky="we", pady=3)
        ttk.Label(grid, text="データベースの URL:").grid(row=1, column=0, sticky="w", pady=3)
        self.url_var = tk.StringVar(value=self.settings["database_url"])
        ttk.Entry(grid, textvariable=self.url_var, width=56).grid(row=1, column=1, sticky="we", pady=3)
        grid.columnconfigure(1, weight=1)

        row = ttk.Frame(f)
        row.pack(fill=tk.X, pady=6)
        self.btn_connect = ttk.Button(row, text="接続して列を読み込む", command=self.on_connect)
        self.btn_connect.pack(side=tk.LEFT)
        self.lbl_status = ttk.Label(row, text="", foreground=C.MUTED)
        self.lbl_status.pack(side=tk.LEFT, padx=8)

        self.map_frame = ttk.LabelFrame(f, text="アプリの項目 → Notion の列", padding=(0, 2, 0, 10))
        self.map_frame.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

        bar = ttk.Frame(self, padding=10)
        bar.pack(fill=tk.X)
        pin_bottom_bar(bar)
        ttk.Button(bar, text="保存", style="Accent.TButton", command=self.on_save).pack(side=tk.RIGHT, padx=5)
        ttk.Button(bar, text="キャンセル", command=self.destroy).pack(side=tk.RIGHT)

    def on_connect(self):
        token, url = self.token_var.get().strip(), self.url_var.get().strip()
        try:
            database_id = notion_sync.database_id_from_url(url)
        except notion_sync.NotionError as e:
            messagebox.showerror("Notion", str(e), parent=self)
            return

        self.btn_connect.state(["disabled"])
        self.lbl_status.config(text="接続中…")
        api_base = self.settings["api_base"]

        def work():
            client = notion_sync.NotionClient(token, api_base)
            title, sources = client.data_sources(database_id)
            ds = sources[0][0]
            return title, sources, ds, client.schema(ds)

        def done(result, error):
            self.btn_connect.state(["!disabled"])
            if error:
                self.lbl_status.config(text="接続できませんでした")
                messagebox.showerror("Notion", str(error), parent=self)
                return
            title, self.sources, ds, self.schema = result
            self.data_source_id = ds
            self.lbl_status.config(text=f"「{title}」に接続しました")
            self.build_mapping(notion_sync.guess_mapping(self.schema))

        run_in_thread(self, work, done)

    def build_mapping(self, mapping):
        for w in self.map_frame.winfo_children():
            w.destroy()
        self.map_vars.clear()
        none = "（使わない）"
        for i, (key, label, types, _) in enumerate(notion_sync.FIELDS):
            cols = [n for n, t in self.schema.items() if t in types]
            cell = ttk.Frame(self.map_frame)
            cell.grid(row=i // 2, column=i % 2, sticky="we", padx=(0, 16) if i % 2 == 0 else 0, pady=(0, 8))
            head = ttk.Frame(cell)
            head.pack(fill=tk.X)
            ttk.Label(head, text=label, font=FONT_SMALL_BOLD).pack(side=tk.LEFT)
            var = tk.StringVar(value=mapping.get(key) if mapping.get(key) in cols else none)
            box = ttk.Combobox(cell, textvariable=var, values=[none] + cols, state="readonly")
            box.pack(fill=tk.X, pady=(2, 0))
            self.map_vars[key] = var
        self.map_frame.columnconfigure(0, weight=1, uniform="map")
        self.map_frame.columnconfigure(1, weight=1, uniform="map")

    def on_save(self):
        token = self.token_var.get().strip()
        url = self.url_var.get().strip()
        if not self.map_vars:
            messagebox.showwarning("Notion", "先に「接続して列を読み込む」を押してください。", parent=self)
            return
        mapping = {k: v.get() for k, v in self.map_vars.items() if v.get() and v.get() != "（使わない）"}
        problem = notion_sync.check_mapping(self.schema, mapping)
        if problem:
            messagebox.showwarning("Notion", problem, parent=self)
            return
        ds = getattr(self, "data_source_id", None) or self.settings["data_source_id"]
        st = settings_store()
        st.set_secret("notion", "token", token, save=False)
        st.set("notion", "database_url", url, save=False)
        st.set("notion", "data_source_id", ds, save=False)
        st.set_json("notion", "mapping", mapping, save=False)
        st.set_json("notion", "schema", self.schema, save=False)
        try:
            st.save()
        except OSError as e:
            messagebox.showerror("Notion", f"設定ファイルに保存できませんでした:\n{e}", parent=self)
            return
        messagebox.showinfo("Notion", "設定を保存しました。", parent=self)
        self.destroy()


# ==============================================================================
# 6. メイン画面
# ==============================================================================
PLAY_STATUS = [("", "未通過"), ("pl", "PL通過"), ("kp", "KP済み")]
PLAY_STATUS_LABEL = dict(PLAY_STATUS)
NAV_ITEMS = [
    ("all", "蔵書のすべて", "books", C.ACCENT_TEXT),
    ("fav", "お気に入り", "star", C.STAR),
]
VIEW_MODES = [("shelf", "本棚"), ("list", "一覧表")]
BOOK_SIZES = [("M", "中"), ("S", "小")]
BOOK_DIMENSIONS = {"M": (132, 186, 20), "S": (96, 136, 14)}

# しおり（ブックマーク）設定項目と連想色
BOOKMARK_ITEMS = [
    ("CoC", "#1b5e20"),      # 深緑（クトゥルフ神話TRPG）
    ("マダミス", "#6a1b9a"),  # 紫（マーダーミステリー）
    ("その他", "#546e7a"),    # スレートグレー
    ("GM可", "#d48806"),     # ゴールド（GM可能）
    ("未通過", "#1565c0"),    # ブルー（未通過）
    ("通過済み", "#c62828"),  # 真紅（通過済み）
]
BOOKMARK_COLORS = dict(BOOKMARK_ITEMS)


class SlideDetailPanel(tk.Frame):
    """画面下部からスライドインするシナリオ詳細プレビューパネル"""
    HEIGHT = 105

    def __init__(self, parent, app):
        super().__init__(
            parent,
            background=C.SURFACE,
            highlightthickness=1,
            highlightbackground=C.BORDER_STRONG,
            cursor="hand2",
        )
        self.app = app
        self.current_id = None
        self.target_y = self.HEIGHT + 20
        self.current_y = self.HEIGHT + 20
        self.anim_job = None
        self.hide_job = None
        self.photo = None

        self._setup_ui()
        self.place(relx=0, rely=1.0, relwidth=1.0, y=self.current_y, height=self.HEIGHT)

    def _setup_ui(self):
        # 最上部の細いアクセントゴールド線
        top_line = tk.Frame(self, background=C.ACCENT, height=2)
        top_line.pack(side=tk.TOP, fill=tk.X)

        body = tk.Frame(self, background=C.SURFACE, padx=16, pady=8)
        body.pack(fill=tk.BOTH, expand=True)

        # 左側サムネイル
        self.lbl_cover = tk.Label(body, background=C.SURFACE, borderwidth=0)
        self.lbl_cover.pack(side=tk.LEFT, padx=(0, 14))

        # 情報カラム
        info_col = tk.Frame(body, background=C.SURFACE)
        info_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 題名 & しおりタグ & 作者行
        title_row = tk.Frame(info_col, background=C.SURFACE)
        title_row.pack(fill=tk.X, anchor="w")

        self.lbl_title = tk.Label(
            title_row, text="", font=FONT_TITLE, foreground=C.ACCENT_TEXT, background=C.SURFACE
        )
        self.lbl_title.pack(side=tk.LEFT)

        # タイトル右側のしおりタグコンテナ（横並び）
        self.bkm_frame = tk.Frame(title_row, background=C.SURFACE)
        self.bkm_frame.pack(side=tk.LEFT, padx=(10, 0))

        self.lbl_author = tk.Label(
            title_row, text="", font=FONT_SMALL, foreground=C.MUTED, background=C.SURFACE
        )
        self.lbl_author.pack(side=tk.LEFT, padx=(10, 0))

        # メタタグ行 (システム, PL人数, 所要時間)
        meta_row = tk.Frame(info_col, background=C.SURFACE)
        meta_row.pack(fill=tk.X, anchor="w", pady=(3, 2))

        self.lbl_meta = tk.Label(
            meta_row, text="", font=FONT_SMALL_BOLD, foreground=C.FAINT, background=C.SURFACE
        )
        self.lbl_meta.pack(side=tk.LEFT)

        # 概要/あらすじ
        self.lbl_synopsis = tk.Label(
            info_col, text="", font=FONT_SMALL, foreground=C.TEXT, background=C.SURFACE,
            anchor="w", justify=tk.LEFT
        )
        self.lbl_synopsis.pack(fill=tk.X, anchor="w", pady=(1, 0))

        # クリックイベントの登録（パネル全体をクリック可能に）
        for w in (self, top_line, body, self.lbl_cover, info_col, title_row, self.lbl_title,
                 self.lbl_author, meta_row, self.lbl_meta, self.lbl_synopsis, self.bkm_frame):
            w.bind("<Button-1>", self._on_click)
            w.bind("<Enter>", self._on_panel_enter)
            w.bind("<Leave>", self._on_panel_leave)

    def _on_click(self, e):
        if self.current_id:
            self.app.select_item(self.current_id)

    def _on_panel_enter(self, e):
        if self.hide_job:
            self.after_cancel(self.hide_job)
            self.hide_job = None

    def _on_panel_leave(self, e):
        self.hide(delay_ms=200)

    def show_record(self, rec):
        if self.hide_job:
            self.after_cancel(self.hide_job)
            self.hide_job = None

        self.current_id = rec.get("id")
        title = rec.get("title") or "（名称未設定）"
        author = f"作: {rec['author']}" if rec.get("author") else ""
        system = rec.get("system_name") or ""
        players = f"👥 {rec['players_text']}" if rec.get("players_text") else ""
        duration = f"⏱️ {rec['duration_text']}" if rec.get("duration_text") else ""

        meta_parts = [p for p in (system, players, duration) if p]
        meta_text = "   |   ".join(meta_parts)

        synopsis = (rec.get("overview") or rec.get("synopsis") or "").strip().replace("\n", " ")
        if len(synopsis) > 110:
            synopsis = synopsis[:110] + "…"

        self.lbl_title.config(text=title)
        self.lbl_author.config(text=author)
        self.lbl_meta.config(text=meta_text)
        self.lbl_synopsis.config(text=synopsis)

        # サムネイル表示
        thumb_bytes = rec.get("thumbnail")
        if thumb_bytes:
            try:
                img = Image.open(io.BytesIO(thumb_bytes))
                img.thumbnail((60, 80))
                self.photo = ImageTk.PhotoImage(img)
                self.lbl_cover.config(image=self.photo, text="")
            except Exception:
                self.lbl_cover.config(image="", text="[画像]")
        else:
            self.lbl_cover.config(image="", text="[表紙なし]")

        # しおり風マークの表示更新（タイトルの右側に横並び）
        for w in self.bkm_frame.winfo_children():
            w.destroy()

        rec_tags = {t[1] if isinstance(t, (tuple, list)) and len(t) >= 2 else t for t in (rec.get("tags") or [])}
        if not rec_tags and self.current_id:
            rec_tags = {t[1] for t in self.app.db.get_item_tags(self.current_id)}

        matched_bkm = [(name, color) for name, color in BOOKMARK_ITEMS if name in rec_tags]
        if matched_bkm:
            for name, color in matched_bkm:
                bkm = tk.Label(
                    self.bkm_frame, text=name,
                    font=FONT_SMALL_BOLD, foreground="#ffffff", background=color,
                    padx=7, pady=1, relief="flat", cursor="hand2"
                )
                bkm.pack(side=tk.LEFT, padx=(0, 6))
                bkm.bind("<Button-1>", self._on_click)
                bkm.bind("<Enter>", self._on_panel_enter)
                bkm.bind("<Leave>", self._on_panel_leave)

        # スライドイン目標
        self.target_y = -self.HEIGHT
        self._start_animation()

    def hide(self, delay_ms=150):
        if self.hide_job:
            self.after_cancel(self.hide_job)
        self.hide_job = self.after(delay_ms, self._do_hide)

    def _do_hide(self):
        self.hide_job = None
        self.target_y = self.HEIGHT + 20
        self._start_animation()

    def _start_animation(self):
        if self.anim_job:
            self.after_cancel(self.anim_job)
        self._step_animation()

    def _step_animation(self):
        diff = self.target_y - self.current_y
        if abs(diff) < 1.0:
            self.current_y = self.target_y
            self.place_configure(y=round(self.current_y))
            self.anim_job = None
            return

        # ゆったりとした上品なイージング (Ease-out)
        step = diff * 0.12
        if abs(step) < 0.6:
            step = 0.6 if diff > 0 else -0.6
        self.current_y += step
        self.place_configure(y=round(self.current_y))
        self.anim_job = self.after(16, self._step_animation)


if sys.platform == "win32":
    class _WinPoint(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class BookmarkTagPopupMenu(tk.Toplevel):
    """
    表紙右クリックで表示される複数選択対応のタグ・しおり設定ポップアップ。
    ユーザーが項目を自由に複数チェック/解除でき、
    枠外（欄外）をクリックした時点でチェックした内容をDBへ一括反映して自動で閉じます。
    """
    def __init__(self, parent, app, item_id, x_root, y_root):
        super().__init__(parent)
        self.app = app
        self.item_id = item_id
        self._applied = False
        self._created_at = time.time()
        self._mouse_released = False

        # ウィンドウ装飾除去・最前面設定
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(background=C.BORDER_STRONG, padx=1, pady=1)  # 1pxの上品な外枠

        # 内部コンテナ
        self.inner = tk.Frame(self, background=C.SURFACE, padx=10, pady=8)
        self.inner.pack(fill=tk.BOTH, expand=True)

        # ヘッダー（タイトル表示）
        header = tk.Frame(self.inner, background=C.SURFACE)
        header.pack(fill=tk.X, pady=(2, 6))

        tk.Label(
            header, text="タグ・しおり設定",
            font=FONT_SMALL_BOLD, foreground=C.ACCENT_TEXT, background=C.SURFACE
        ).pack(side=tk.LEFT)

        sep = tk.Frame(self.inner, background=C.BORDER, height=1)
        sep.pack(fill=tk.X, pady=(0, 4))

        # 現在のタグ取得
        current_tags = {t[1] for t in self.app.db.get_item_tags(item_id)}
        self.tag_states = {}
        self.rows = []

        for name, color in BOOKMARK_ITEMS:
            is_checked = (name in current_tags)
            self.tag_states[name] = is_checked
            self._create_tag_row(name, color, is_checked)

        sep_b = tk.Frame(self.inner, background=C.BORDER, height=1)
        sep_b.pack(fill=tk.X, pady=(6, 4))

        tk.Label(
            self.inner, text="※欄外クリックで保存して閉じます",
            font=FONT_CAPTION, foreground=C.FAINT, background=C.SURFACE
        ).pack(anchor="center", pady=(0, 2))

        # 画面端での見切れ防止座標計算
        self.update_idletasks()
        pw = self.winfo_reqwidth()
        ph = self.winfo_reqheight()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()

        target_x = min(max(10, x_root), sw - pw - 10)
        target_y = min(max(10, y_root), sh - ph - 40)
        self.geometry(f"+{target_x}+{target_y}")

        self.bind("<Escape>", lambda e: self.close_and_apply())
        self.bind("<Return>", lambda e: self.close_and_apply())

        self._poll_job = self.after(50, self._check_outside_click)

    def _create_tag_row(self, name, color, is_checked):
        row = tk.Frame(self.inner, background=C.SURFACE, cursor="hand2", padx=4, pady=3)
        row.pack(fill=tk.X, pady=1)
        self.rows.append(row)

        check_text = "☑" if is_checked else "☐"
        check_fg = C.ACCENT_TEXT if is_checked else C.FAINT
        check_lbl = tk.Label(
            row, text=check_text, font=("Segoe UI", 10),
            foreground=check_fg, background=C.SURFACE, width=2, cursor="hand2"
        )
        check_lbl.pack(side=tk.LEFT)

        canv = tk.Canvas(row, width=14, height=16, background=C.SURFACE, highlightthickness=0, cursor="hand2")
        canv.pack(side=tk.LEFT, padx=(2, 6))
        pts = [2, 1, 12, 1, 12, 15, 7, 12, 2, 15]
        canv.create_polygon(pts, fill=color, outline="")

        name_lbl = tk.Label(
            row, text=name, font=FONT_SMALL,
            foreground=C.TEXT, background=C.SURFACE, cursor="hand2"
        )
        name_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

        widgets = (row, check_lbl, canv, name_lbl)

        def set_bg(bg):
            row.configure(background=bg)
            check_lbl.configure(background=bg)
            canv.configure(background=bg)
            name_lbl.configure(background=bg)

        def on_enter(e):
            set_bg(C.HOVER)

        def on_leave(e):
            set_bg(C.SURFACE)

        def on_toggle(e=None):
            new_val = not self.tag_states[name]
            self.tag_states[name] = new_val
            check_lbl.configure(
                text="☑" if new_val else "☐",
                foreground=C.ACCENT_TEXT if new_val else C.FAINT
            )

        for w in widgets:
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)
            w.bind("<Button-1>", on_toggle)

    def _check_outside_click(self):
        if not self.winfo_exists() or self._applied:
            return

        if sys.platform == "win32":
            l_down = bool(ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000)
            r_down = bool(ctypes.windll.user32.GetAsyncKeyState(0x02) & 0x8000)

            if not self._mouse_released:
                if not l_down and not r_down and (time.time() - self._created_at > 0.1):
                    self._mouse_released = True
                self._poll_job = self.after(40, self._check_outside_click)
                return

            if l_down or r_down:
                pt = _WinPoint()
                ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
                wx = self.winfo_rootx()
                wy = self.winfo_rooty()
                ww = self.winfo_width()
                wh = self.winfo_height()

                if not (wx <= pt.x <= wx + ww and wy <= pt.y <= wy + wh):
                    self.close_and_apply()
                    return

        self._poll_job = self.after(40, self._check_outside_click)

    def close_and_apply(self):
        if self._applied:
            return
        self._applied = True
        if self._poll_job:
            self.after_cancel(self._poll_job)
            self._poll_job = None

        current_tags = {t[1] for t in self.app.db.get_item_tags(self.item_id)}
        changed = False
        for name, checked in self.tag_states.items():
            if checked != (name in current_tags):
                self.app.db.toggle_item_tag(self.item_id, name, checked)
                changed = True

        if changed:
            self.app.refresh()
            if hasattr(self.app, "slide_panel") and self.app.slide_panel.current_id == self.item_id:
                rec = next((r for r in self.app.records if r["id"] == self.item_id), None)
                if rec:
                    self.app.slide_panel.show_record(rec)

        if getattr(self.app, "tag_popup", None) == self:
            self.app.tag_popup = None

        self.destroy()


class ShelfView(tk.Canvas):
    def __init__(self, parent, app):
        super().__init__(parent, background=C.BG, highlightthickness=0, yscrollincrement=24)
        self.app = app
        self.records = []
        self.mode = "shelf"
        self.size = "M"
        self.rects = {}
        self.book_items = {}
        self.hover_id = None
        self._anim_job = None
        self.selected = None
        self._last_width = 0
        self._resize_job = None
        self._menu_vars = {}

        self.bind("<Button-1>", self._on_click)
        self.bind("<Button-3>", self._on_right_click)
        self.bind("<Motion>", self._on_mouse_move)
        self.bind("<Leave>", self._on_mouse_leave)
        self.bind("<Configure>", self._on_configure)
        self.bind("<MouseWheel>", self._on_mouse_wheel)
        self.bind("<Button-4>", lambda e: self._on_mouse_wheel(e, up=True))
        self.bind("<Button-5>", lambda e: self._on_mouse_wheel(e, up=False))

    def _on_mouse_wheel(self, event, up=None):
        if getattr(self.app, "_is_window_dragging", False):
            return
        if hasattr(self.app, "tag_popup") and self.app.tag_popup and self.app.tag_popup.winfo_exists():
            self.app.tag_popup.close_and_apply()
        if up is None:
            up = event.delta > 0
        delta = -3 if up else 3
        self.yview_scroll(delta, "units")
        self._on_mouse_move(event)
        return "break"

    def _on_configure(self, event):
        # ウィンドウ移動中は本棚の再レイアウトを抑制（ドラッグ移動中のチラつき・表示崩れを完全防止）
        if getattr(self.app, "_is_window_dragging", False):
            return
        # ウィンドウの端をD&Dしてリサイズした際、本棚の列数・配置を追随させる
        if abs(event.width - self._last_width) >= 12:
            self._last_width = event.width
            if self._resize_job:
                self.after_cancel(self._resize_job)
            self._resize_job = self.after(30, self._re_layout)

    def _re_layout(self):
        self._resize_job = None
        if self.records:
            self.show(self.records, self.mode, self.size, selected=self.selected, keep_scroll=True)

    def show(self, records, mode, size, selected=None, keep_scroll=False):
        if self._anim_job:
            self.after_cancel(self._anim_job)
            self._anim_job = None

        prev_yview = self.yview()[0] if (keep_scroll and self.records) else 0.0

        self.records, self.mode, self.size, self.selected = records, mode, size, selected
        self.delete("all")
        self.rects.clear()
        self.book_items.clear()
        self.hover_id = None

        if not self.records:
            width = max(self.winfo_width(), 600)
            height = max(self.winfo_height(), 400)
            kw = self.app.search_var.get().strip() if hasattr(self.app, "search_var") else ""
            if kw:
                msg = f"「{kw}」に一致するシナリオは見つかりませんでした"
            else:
                msg = "📖 本棚にシナリオがありません\n\nPDF または ZIP ファイルをここにドラッグ＆ドロップして追加できます"
            self.create_text(
                width // 2, height // 2 - 20,
                text=msg,
                fill=C.FAINT,
                font=FONT,
                justify=tk.CENTER
            )
            self.configure(scrollregion=(0, 0, width, height))
            return

        width = max(self.winfo_width(), 600)
        bw, bh, gap = BOOK_DIMENSIONS.get(size, BOOK_DIMENSIONS["M"])
        per = max(1, (width - 60) // (bw + gap))
        y = 24
        for i, rec in enumerate(self.records):
            col = i % per
            x = 30 + col * (bw + gap)
            if col == 0 and i > 0:
                y += bh + 48
            top = y
            self.rects[rec["id"]] = (x, top, x + bw, top + bh)
            tag = f"b{rec['id']}"

            # 浮き上がった際に背後に残る影
            shadow_tag = f"sh_{rec['id']}"
            sh_img = book_shadow_photo(self, bw, bh, strength=0.6)
            self.create_image(x - 14, top - 14 + 6, image=sh_img, anchor="nw", tags=(shadow_tag,))

            # 本の画像
            bk_img = book_photo(self, (rec["id"], rec.get("title")), rec["thumbnail"], rec["title"], bw, bh)
            self.create_image(x, top, image=bk_img, anchor="nw", tags=(tag, "book"))

            # タグに含まれるしおり項目の抽出としおり風リボンマークの描画（本の右上）
            rec_tags = {t[1] if isinstance(t, (tuple, list)) and len(t) >= 2 else t for t in (rec.get("tags") or [])}
            matched_bkm = [(name, color) for name, color in BOOKMARK_ITEMS if name in rec_tags]
            bkm_polygons = []
            if matched_bkm:
                bx_start = x + bw - 14
                by_top = top - 4  # 本の天面から少し飛び出す
                rw, rh, notch = 11, 25, 5
                for bi, (bname, bcolor) in enumerate(matched_bkm):
                    bx = bx_start - bi * 13
                    pts = [
                        bx, by_top,
                        bx + rw, by_top,
                        bx + rw, by_top + rh,
                        bx + rw / 2.0, by_top + rh - notch,
                        bx, by_top + rh,
                    ]
                    pid = self.create_polygon(
                        pts, fill=bcolor, outline=C.BG, width=1,
                        tags=(tag, f"bkm_{rec['id']}")
                    )
                    bkm_polygons.append((pid, pts))

            self.book_items[rec["id"]] = {
                "tag": tag,
                "shadow_tag": shadow_tag,
                "bkm_polygons": bkm_polygons,
                "base_x": x,
                "base_y": top,
                "bw": bw,
                "bh": bh,
                "offset_x": 0.0,
                "offset_y": 0.0,
                "target_offset_x": 0.0,
                "target_offset_y": 0.0,
                "rec": rec,
            }

        self.configure(scrollregion=(0, 0, width, y + bh + 48))
        if keep_scroll:
            self.yview_moveto(prev_yview)

    def _on_mouse_move(self, e):
        cx, cy = self.canvasx(e.x), self.canvasy(e.y)
        found_id = None
        for iid, (x1, y1, x2, y2) in self.rects.items():
            if x1 - 10 <= cx <= x2 + 10 and y1 - 10 <= cy <= y2 + 10:
                found_id = iid
                break

        if found_id != self.hover_id:
            # 以前の本を元の位置へ戻す
            if self.hover_id and self.hover_id in self.book_items:
                self.book_items[self.hover_id]["target_offset_x"] = 0.0
                self.book_items[self.hover_id]["target_offset_y"] = 0.0

            self.hover_id = found_id
            if self.hover_id and self.hover_id in self.book_items:
                item_data = self.book_items[self.hover_id]

                # 本棚の可視領域の中央座標（スクロール考慮）
                view_w = max(self.winfo_width(), 600)
                view_h = max(self.winfo_height(), 400)
                shelf_center_x = self.canvasx(view_w / 2.0)
                shelf_center_y = self.canvasy(view_h / 2.0)

                # 本の中心座標
                book_center_x = item_data["base_x"] + item_data["bw"] / 2.0
                book_center_y = item_data["base_y"] + item_data["bh"] / 2.0

                # 本棚中央へのベクトル方向
                vec_x = shelf_center_x - book_center_x
                vec_y = shelf_center_y - book_center_y
                dist = math.hypot(vec_x, vec_y)

                if dist > 1.0:
                    # 本棚の中央方向へふわりと吸い寄せられる（最大13px）
                    pull_len = min(13.0, max(4.0, dist * 0.05))
                    target_x = (vec_x / dist) * pull_len
                    target_y = (vec_y / dist) * pull_len
                else:
                    target_x = 0.0
                    target_y = -3.0

                item_data["target_offset_x"] = target_x
                item_data["target_offset_y"] = target_y

                self.config(cursor="hand2")
                if hasattr(self.app, "slide_panel") and self.app.slide_panel:
                    self.app.slide_panel.show_record(item_data["rec"])
            else:
                self.config(cursor="")
                if hasattr(self.app, "slide_panel") and self.app.slide_panel:
                    self.app.slide_panel.hide()

            self._start_anim()

    def _on_mouse_leave(self, e):
        if self.hover_id and self.hover_id in self.book_items:
            self.book_items[self.hover_id]["target_offset_x"] = 0.0
            self.book_items[self.hover_id]["target_offset_y"] = 0.0
        self.hover_id = None
        self.config(cursor="")
        if hasattr(self.app, "slide_panel") and self.app.slide_panel:
            self.app.slide_panel.hide()
        self._start_anim()

    def _start_anim(self):
        if self._anim_job:
            self.after_cancel(self._anim_job)
        self._step_anim()

    def _step_anim(self):
        moving = False
        for data in self.book_items.values():
            curr_x = data["offset_x"]
            target_x = data["target_offset_x"]
            diff_x = target_x - curr_x

            curr_y = data["offset_y"]
            target_y = data["target_offset_y"]
            diff_y = target_y - curr_y

            # X 方向のゆったりとした滑らかなイージング補間
            if abs(diff_x) > 0.15:
                step_x = diff_x * 0.10
                if abs(step_x) < 0.2:
                    step_x = 0.2 if diff_x > 0 else -0.2
                data["offset_x"] += step_x
                moving = True
            elif curr_x != target_x:
                data["offset_x"] = target_x

            # Y 方向のゆったりとした滑らかなイージング補間
            if abs(diff_y) > 0.15:
                step_y = diff_y * 0.10
                if abs(step_y) < 0.2:
                    step_y = 0.2 if diff_y > 0 else -0.2
                data["offset_y"] += step_y
                moving = True
            elif curr_y != target_y:
                data["offset_y"] = target_y

            new_x = round(data["base_x"] + data["offset_x"])
            new_y = round(data["base_y"] + data["offset_y"])
            self.coords(data["tag"], new_x, new_y)

            # しおり風マークも本と一緒にふわりと浮上連動
            for pid, base_pts in data.get("bkm_polygons", []):
                new_pts = []
                for pi, val in enumerate(base_pts):
                    off = data["offset_x"] if pi % 2 == 0 else data["offset_y"]
                    new_pts.append(round(val + off))
                self.coords(pid, *new_pts)

            # 影（シャドウ）は奥に残りつつ、中央引き寄せに連動
            sh_x = round(data["base_x"] - 14 + data["offset_x"] * 0.2)
            sh_y = round(data["base_y"] - 14 + 6 + data["offset_y"] * 0.2)
            self.coords(data["shadow_tag"], sh_x, sh_y)

        if moving:
            self._anim_job = self.after(16, self._step_anim)
        else:
            self._anim_job = None

    def _on_click(self, e):
        if hasattr(self.app, "tag_popup") and self.app.tag_popup and self.app.tag_popup.winfo_exists():
            self.app.tag_popup.close_and_apply()
        cx, cy = self.canvasx(e.x), self.canvasy(e.y)
        for iid, (x1, y1, x2, y2) in self.rects.items():
            if x1 - 12 <= cx <= x2 + 12 and y1 - 12 <= cy <= y2 + 12:
                self.app.select_item(iid)
                return
        self.app.select_item(None)

    def _on_right_click(self, e):
        """シナリオ表紙を右クリックした際にチェック項目メニューを表示"""
        if hasattr(self.app, "tag_popup") and self.app.tag_popup and self.app.tag_popup.winfo_exists():
            self.app.tag_popup.close_and_apply()

        cx, cy = self.canvasx(e.x), self.canvasy(e.y)
        found_id = None
        for iid, (x1, y1, x2, y2) in self.rects.items():
            if x1 - 10 <= cx <= x2 + 10 and y1 - 10 <= cy <= y2 + 10:
                found_id = iid
                break
        if not found_id:
            return

        self._show_bookmark_menu(e, found_id)

    def _show_bookmark_menu(self, e, item_id):
        """チェックマーク付き複数選択ポップアップ（欄外クリックで自動保存・反映）"""
        if hasattr(self.app, "tag_popup") and self.app.tag_popup and self.app.tag_popup.winfo_exists():
            self.app.tag_popup.close_and_apply()
        self.app.tag_popup = BookmarkTagPopupMenu(self, self.app, item_id, e.x_root, e.y_root)

    def _toggle_bookmark(self, item_id, name, enabled):
        """右クリックメニューでのチェック切り替え（DBタグへの反映としおり更新）"""
        self.app.db.toggle_item_tag(item_id, name, enabled)
        # 本棚一覧の更新
        self.app.refresh()
        # スライドパネルが開いていれば更新
        if hasattr(self.app, "slide_panel") and self.app.slide_panel.current_id == item_id:
            rec = next((r for r in self.app.records if r["id"] == item_id), None)
            if rec:
                self.app.slide_panel.show_record(rec)


def is_scenario_file(filename):
    ext = os.path.splitext(filename)[1].lower()
    return ext in {".pdf", ".zip"}


def collect_scenario_targets(paths):
    """
    与えられたパスリスト（ファイルまたはフォルダ）から、
    「1フォルダ=1シナリオ」、または「1ファイル=1シナリオ」として取り込み対象を収集する。
    1つのフォルダ内の複数PDF/ZIPをバラバラに登録せず、フォルダ全体で1つのシナリオとして扱う。
    """
    results = []
    seen = set()

    def add_target(p):
        norm = os.path.abspath(p)
        if norm not in seen and os.path.exists(norm):
            seen.add(norm)
            results.append(norm)

    for p in paths:
        if isinstance(p, bytes):
            try:
                p = p.decode("utf-8")
            except UnicodeDecodeError:
                p = p.decode("cp932", errors="replace")

        p = os.path.abspath(p)
        if not os.path.exists(p):
            continue

        if os.path.isdir(p):
            # フォルダの場合：直下にファイル（PDF, ZIP, TXT等）があるか確認
            has_direct_files = False
            sub_dirs = []
            try:
                for entry in os.scandir(p):
                    if entry.is_file() and not entry.name.startswith("."):
                        has_direct_files = True
                    elif entry.is_dir() and not entry.name.startswith("."):
                        sub_dirs.append(entry.path)
            except Exception:
                pass

            if has_direct_files or not sub_dirs:
                # 直下にファイルが存在する、または子フォルダが存在しない場合は、このフォルダ自身を1つのシナリオとする
                add_target(p)
            else:
                # 直下にファイルがなく子フォルダが並んでいる場合は、まとめ親フォルダとみなして各子フォルダを1つのシナリオとする
                for sub in sub_dirs:
                    add_target(sub)

        elif os.path.isfile(p):
            if is_scenario_file(p):
                add_target(p)

    return results


collect_scenario_files = collect_scenario_targets


def parse_name_clues(name):
    """
    フォルダ名やファイル名からシステム名、タイトル、タグのヒントを抽出する。
    例:
      '【CoC】海も枯れるまで' -> system: 'クトゥルフ神話TRPG', title: '海も枯れるまで', tags: ['CoC']
      '[マダミス]狂気山脈' -> system: 'マーダーミステリー', title: '狂気山脈', tags: ['マダミス']
    """
    clean_name = os.path.splitext(name)[0]
    clues = {"title": clean_name, "system_name": None, "tags": []}

    sys_patterns = [
        (r"(?i)\b(CoC|クトゥルフ|Call of Cthulhu)\b", "クトゥルフ神話TRPG", "CoC"),
        (r"(?i)\b(マダミス|マーダーミステリー|Murder Mystery)\b", "マーダーミステリー", "マダミス"),
        (r"(?i)\b(エモクロア|Emoklore)\b", "エモクロアTRPG", "その他"),
        (r"(?i)\b(インセイン|inSANe)\b", "インセイン", "その他"),
        (r"(?i)\b(シノビガミ|Shinobigami)\b", "シノビガミ", "その他"),
        (r"(?i)\b(マギカロギア|Magicarogia)\b", "マギカロギア", "その他"),
        (r"(?i)\b(フタリソウサ)\b", "フタリソウサ", "その他"),
        (r"(?i)\b(ソード・ワールド|SW2\.5|SW2\.0)\b", "ソード・ワールド2.5", "その他"),
        (r"(?i)\b(ダブルクロス|DX3rd)\b", "ダブルクロス The 3rd Edition", "その他"),
    ]

    for pat, sys_name, tag in sys_patterns:
        if re.search(pat, clean_name):
            clues["system_name"] = sys_name
            if tag:
                clues["tags"].append(tag)
            break

    # 【...】や [...] や (...) を除去したものをタイトル候補にする
    t = re.sub(r"^[【\[［\(（][^】\]］\)）]+[】\]］\)）]\s*", "", clean_name)
    t = re.sub(r"\s*[【\[［\(（][^】\]］\)）]+[】\]］\)）]$", "", t)
    m = re.search(r"[「『]([^」』]+)[」』]", clean_name)
    if m:
        t = m.group(1)

    t = t.strip()
    if t and len(t) >= 2:
        clues["title"] = t

    return clues


def search_fallback_cover(target_path):
    """フォルダ内またはZIP内から表紙画像の候補を探索してJPEGバイト列として返す"""
    valid_exts = {".png", ".jpg", ".jpeg", ".webp"}
    candidates = []

    if os.path.isdir(target_path):
        for root, _, files in os.walk(target_path):
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in valid_exts:
                    candidates.append((f.lower(), os.path.join(root, f)))
    elif os.path.isfile(target_path) and target_path.lower().endswith(".zip"):
        try:
            with zipfile.ZipFile(target_path, "r") as z:
                for info in z.infolist():
                    if info.is_dir():
                        continue
                    fname = os.path.basename(info.filename)
                    ext = os.path.splitext(fname)[1].lower()
                    if ext in valid_exts:
                        candidates.append((fname.lower(), (target_path, info.filename)))
        except Exception:
            pass

    if not candidates:
        return None

    def score(item):
        name = item[0]
        s = 0
        if any(k in name for k in ["cover", "表紙", "thumb", "main", "title", "トレーラー", "top", "01"]):
            s += 50
        if not any(k in name for k in ["icon", "map", "npc", "立ち絵", "token", "bg", "chip"]):
            s += 10
        return s

    candidates.sort(key=score, reverse=True)
    best = candidates[0][1]

    try:
        if isinstance(best, tuple):
            with zipfile.ZipFile(best[0], "r") as z:
                data = z.read(best[1])
        else:
            with open(best, "rb") as f:
                data = f.read()

        img = Image.open(io.BytesIO(data))
        img.thumbnail((450, 450))
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    except Exception:
        return None


def search_fallback_texts(target_path):
    """フォルダ内またはZIP内からあらすじ・概要になりそうなテキストを探索して返す"""
    valid_exts = {".txt", ".md", ".html"}
    candidates = []

    if os.path.isdir(target_path):
        for root, _, files in os.walk(target_path):
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in valid_exts:
                    candidates.append((f.lower(), os.path.join(root, f)))
    elif os.path.isfile(target_path) and target_path.lower().endswith(".zip"):
        try:
            with zipfile.ZipFile(target_path, "r") as z:
                for info in z.infolist():
                    if info.is_dir():
                        continue
                    fname = os.path.basename(info.filename)
                    ext = os.path.splitext(fname)[1].lower()
                    if ext in valid_exts:
                        candidates.append((fname.lower(), (target_path, info.filename)))
        except Exception:
            pass

    if not candidates:
        return None, None

    def score(item):
        name = item[0]
        s = 0
        if any(k in name for k in ["readme", "概要", "シナリオ", "あらすじ", "story", "info", "はじめに"]):
            s += 50
        return s

    candidates.sort(key=score, reverse=True)
    best = candidates[0][1]

    try:
        if isinstance(best, tuple):
            with zipfile.ZipFile(best[0], "r") as z:
                raw_bytes = z.read(best[1])
        else:
            with open(best, "rb") as f:
                raw_bytes = f.read()

        text = ""
        for enc in ("utf-8", "cp932", "euc-jp"):
            try:
                text = raw_bytes.decode(enc)
                break
            except UnicodeDecodeError:
                pass

        if not text:
            return None, None

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return None, None

        synopsis_lines = []
        capture = False
        for l in lines:
            if any(k in l for k in ["【あらすじ】", "【ストーリー】", "【概要】", "■あらすじ", "■ストーリー", "◆あらすじ"]):
                capture = True
                continue
            if capture:
                if any(l.startswith(prefix) for prefix in ["【", "■", "◆", "▼", "・"]):
                    break
                synopsis_lines.append(l)

        if synopsis_lines:
            syn = "\n".join(synopsis_lines[:6])
            return None, syn
        else:
            ov = "\n".join(lines[:4])
            return ov, None
    except Exception:
        return None, None


def extract_scenario_data(extractor, target_path):
    """
    フォルダまたはZIP（または単体ファイル）から情報を統合抽出する。
    1. Rust DLL による抽出
    2. フォルダ名/ファイル名からのタイトル・システム名補正
    3. 表紙画像のフォールバック探索
    4. 概要・あらすじのフォールバック探索
    5. 不足項目の判定
    """
    raw_name = os.path.basename(target_path.rstrip(r"\/"))
    name_clues = parse_name_clues(raw_name)

    thumb_bytes = None
    choices = []
    info = {}

    if extractor:
        try:
            thumb_bytes, choices, info = extractor.run_extract(target_path)
        except Exception as e:
            pass

    fields, auto_tags = parse_info(info)

    # 1. タイトル補正
    ext_title = (fields.get("title") or "").strip()
    generic_words = {"readme", "scenario", "無題", "シナリオ", "本編", "ルールブック", "新規テキスト ドキュメント", "index", "data"}
    if not ext_title or ext_title.lower() in generic_words:
        fields["title"] = name_clues["title"] or raw_name
    elif name_clues.get("title") and len(ext_title) < 4 and len(name_clues["title"]) >= 4:
        fields["title"] = name_clues["title"]

    # 2. システム名補正
    if not fields.get("system_name") and name_clues.get("system_name"):
        fields["system_name"] = name_clues["system_name"]

    # 3. タグ統合
    combined_tags = set(auto_tags)
    for t in name_clues.get("tags", []):
        combined_tags.add(t)

    # 4. 表紙画像のフォールバック補完
    if not thumb_bytes:
        thumb_bytes = search_fallback_cover(target_path)

    # 5. 概要・あらすじのフォールバック補完
    if not fields.get("overview") and not fields.get("synopsis"):
        ov, syn = search_fallback_texts(target_path)
        if ov:
            fields["overview"] = ov
        if syn:
            fields["synopsis"] = syn

    # 6. 不足項目の判定
    missing_items = []
    if not thumb_bytes:
        missing_items.append("表紙画像")
    if not fields.get("system_name"):
        missing_items.append("システム名")
    if not (fields.get("synopsis") or fields.get("overview")):
        missing_items.append("概要・あらすじ")

    return {
        "target_path": target_path,
        "raw_name": raw_name,
        "title": fields.get("title") or raw_name,
        "fields": fields,
        "thumb_bytes": thumb_bytes,
        "tags": combined_tags,
        "missing_items": missing_items,
    }


class ImportProgressDialog(tk.Toplevel):
    """複数シナリオの一括取り込み時の進捗表示ダイアログ"""
    def __init__(self, parent, total):
        super().__init__(parent)
        self.title("シナリオ取り込み中")
        self.geometry("460x170")
        self.configure(background=C.BG)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.is_cancelled = False
        self.total = total

        # ウィンドウ中央配置
        center_on_parent(self, parent, 460, 170)
        self.after_idle(lambda: center_on_parent(self, parent, 460, 170))
        self.after(50, lambda: center_on_parent(self, parent, 460, 170))

        pad = tk.Frame(self, background=C.BG, padx=22, pady=18)
        pad.pack(fill=tk.BOTH, expand=True)

        self.lbl_status = tk.Label(
            pad, text=f"シナリオを取り込んでいます... (0/{total})",
            font=FONT_BOLD, foreground=C.TEXT, background=C.BG, anchor="w"
        )
        self.lbl_status.pack(fill=tk.X, pady=(0, 4))

        self.lbl_file = tk.Label(
            pad, text="",
            font=FONT_SMALL, foreground=C.MUTED, background=C.BG, anchor="w"
        )
        self.lbl_file.pack(fill=tk.X, pady=(0, 12))

        self.prog = ttk.Progressbar(pad, maximum=total, value=0)
        self.prog.pack(fill=tk.X, pady=(0, 14))

        btn_box = tk.Frame(pad, background=C.BG)
        btn_box.pack(fill=tk.X)
        ttk.Button(btn_box, text="中止", command=self._on_cancel, style="Side.TButton").pack(side=tk.RIGHT)

        self.update()

    def _on_cancel(self):
        self.is_cancelled = True
        self.lbl_status.config(text="取り込みを中止しています...")

    def update_progress(self, current, total, filename):
        self.prog["value"] = current
        self.lbl_status.config(text=f"シナリオを取り込んでいます... ({current}/{total})")
        if len(filename) > 38:
            filename = filename[:35] + "..."
        self.lbl_file.config(text=filename)
        self.update()

    def close(self):
        try:
            self.grab_release()
            self.destroy()
        except Exception:
            pass


class ScenarioIncompleteDialog(tk.Toplevel):
    """
    シナリオ取り込み時に情報（表紙画像、システム名、あらすじなど）に不足がある場合に、
    「URLから登録」「手動登録」「そのままにする」を確認・選択するPOPUPダイアログ。
    ボタンやウィンドウの色は主ウィンドウ（CatalogApp）の配色に完全準拠。
    """
    def __init__(self, parent, app, data, item_id, is_multiple=False):
        super().__init__(parent)
        self.app = app
        self.data = data
        self.item_id = item_id
        self.is_multiple = is_multiple
        self.action = "keep"
        self.apply_to_all = False

        self.title("シナリオ情報の確認")
        self.configure(background=C.BG)
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)

        apply_window_titlebar_theme(self, borderless=True)

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self._setup_ui()
        center_on_parent(self, parent, 580, 480)
        self.after_idle(lambda: center_on_parent(self, parent, 580, 480))
        self.after(50, lambda: center_on_parent(self, parent, 580, 480))

    def _setup_ui(self):
        pad = tk.Frame(self, background=C.BG, padx=22, pady=18)
        pad.pack(fill=tk.BOTH, expand=True)

        # 1. タイトルと案内文
        lbl_h = tk.Label(
            pad, text="📖  シナリオ情報の確認",
            font=FONT_TITLE, foreground=C.ACCENT_TEXT, background=C.BG, anchor="w"
        )
        lbl_h.pack(fill=tk.X, pady=(0, 2))

        lbl_desc = tk.Label(
            pad, text="取り込んだシナリオの情報に一部未設定の項目があります。\n登録方法を選択してください。",
            font=FONT_SMALL, foreground=C.MUTED, background=C.BG, anchor="w", justify=tk.LEFT
        )
        lbl_desc.pack(fill=tk.X, pady=(0, 10))

        # 2. プレビューカード (C.SURFACE)
        card = tk.Frame(pad, background=C.SURFACE, highlightbackground=C.BORDER_STRONG, highlightthickness=1, padx=12, pady=10)
        card.pack(fill=tk.X, pady=(0, 10))

        # 表紙画像プレビュー (左側)
        self.lbl_cover = tk.Label(card, background=C.SURFACE_2, width=8, height=4)
        self.lbl_cover.pack(side=tk.LEFT, padx=(0, 14))
        self.photo = None
        if self.data.get("thumb_bytes"):
            try:
                img = Image.open(io.BytesIO(self.data["thumb_bytes"]))
                img.thumbnail((65, 85))
                self.photo = ImageTk.PhotoImage(img)
                self.lbl_cover.config(image=self.photo, width=65, height=85)
            except Exception:
                self.lbl_cover.config(text="[画像]", font=FONT_SMALL, foreground=C.FAINT)
        else:
            self.lbl_cover.config(text="[表紙なし]", font=FONT_SMALL, foreground=C.FAINT)

        # 情報テキスト (右側)
        c_right = tk.Frame(card, background=C.SURFACE)
        c_right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        tk.Label(
            c_right, text=self.data["title"],
            font=FONT_BOLD, foreground=C.TEXT, background=C.SURFACE, anchor="w"
        ).pack(fill=tk.X)

        tk.Label(
            c_right, text=f"元データ: {self.data['raw_name']}",
            font=FONT_CAPTION, foreground=C.MUTED, background=C.SURFACE, anchor="w"
        ).pack(fill=tk.X, pady=(1, 4))

        fields = self.data["fields"]
        sys_txt = fields.get("system_name") or "⚠️ システム名未設定"
        sys_fg = C.TEXT if fields.get("system_name") else "#d48806"
        tk.Label(
            c_right, text=f"システム: {sys_txt}",
            font=FONT_SMALL, foreground=sys_fg, background=C.SURFACE, anchor="w"
        ).pack(fill=tk.X)

        meta_parts = []
        if fields.get("players_text"):
            meta_parts.append(f"👥 {fields['players_text']}")
        if fields.get("duration_text"):
            meta_parts.append(f"⏱️ {fields['duration_text']}")
        meta_str = "   |   ".join(meta_parts) if meta_parts else "⚠️ 人数・時間未設定"
        meta_fg = C.MUTED if meta_parts else "#d48806"
        tk.Label(
            c_right, text=meta_str,
            font=FONT_SMALL, foreground=meta_fg, background=C.SURFACE, anchor="w"
        ).pack(fill=tk.X, pady=(1, 0))

        # あらすじプレビュー
        syn = (fields.get("synopsis") or fields.get("overview") or "").strip().replace("\n", " ")
        if len(syn) > 60:
            syn = syn[:60] + "…"
        syn_txt = f"概要: {syn}" if syn else "⚠️ 概要・あらすじ未設定"
        syn_fg = C.MUTED if syn else "#d48806"
        tk.Label(
            c_right, text=syn_txt,
            font=FONT_SMALL, foreground=syn_fg, background=C.SURFACE, anchor="w"
        ).pack(fill=tk.X, pady=(1, 0))

        # 3. 不足項目アラートバナー (C.SURFACE_2)
        alert_box = tk.Frame(pad, background=C.SURFACE_2, highlightbackground=C.BORDER, highlightthickness=1, padx=10, pady=6)
        alert_box.pack(fill=tk.X, pady=(0, 12))

        tk.Label(
            alert_box, text="⚠️ 未設定の項目:",
            font=FONT_SMALL_BOLD, foreground="#e59a18", background=C.SURFACE_2
        ).pack(side=tk.LEFT, padx=(0, 6))

        for item in self.data["missing_items"]:
            b = tk.Label(
                alert_box, text=item,
                font=FONT_SMALL, foreground="#ffffff", background="#7b2d26", padx=6, pady=1
            )
            b.pack(side=tk.LEFT, padx=(0, 4))

        # 4. 複数シナリオ取り込み時の一括チェックボックス
        self.apply_all_var = tk.BooleanVar(value=False)
        if self.is_multiple:
            cb = ttk.Checkbutton(
                pad, text="以降の不足シナリオも「そのままにする」",
                variable=self.apply_all_var
            )
            cb.pack(anchor="w", pady=(0, 10))

        # 5. インラインURL入力バー（初期状態は非表示）
        self.url_frame = tk.Frame(
            pad, background=C.SURFACE, highlightbackground=C.ACCENT, highlightthickness=1, padx=10, pady=8
        )
        tk.Label(
            self.url_frame, text="URL:", font=FONT_BOLD, foreground=C.ACCENT_TEXT, background=C.SURFACE
        ).pack(side=tk.LEFT, padx=(0, 6))

        self.url_var = tk.StringVar()
        self.entry_url = ttk.Entry(self.url_frame, textvariable=self.url_var, width=34)
        self.entry_url.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        self.entry_url.bind("<Return>", lambda e: self._do_fetch_url())

        self.btn_fetch_submit = ttk.Button(
            self.url_frame, text="取得して反映", style="Accent.TButton", command=self._do_fetch_url
        )
        self.btn_fetch_submit.pack(side=tk.LEFT, padx=(0, 4))

        ttk.Button(
            self.url_frame, text="閉じる", style="Small.TButton", command=self._hide_url_frame
        ).pack(side=tk.LEFT)

        # 6. 操作ボタンエリア (下部)
        self.btn_row = tk.Frame(pad, background=C.BG)
        self.btn_row.pack(fill=tk.X, side=tk.BOTTOM)

        ttk.Button(
            self.btn_row, text="🌐 URLから登録",
            style="Accent.TButton", command=self._on_url
        ).pack(side=tk.LEFT, padx=(0, 8))

        ttk.Button(
            self.btn_row, text="✏️ 手動登録",
            style="TButton", command=self._on_manual
        ).pack(side=tk.LEFT, padx=(0, 8))

        ttk.Button(
            self.btn_row, text="⏩ そのままにする",
            style="Ghost.TButton", command=self._on_keep
        ).pack(side=tk.LEFT, padx=(0, 8))

        ttk.Button(
            self.btn_row, text="キャンセル",
            style="Danger.Small.TButton", command=self._on_cancel
        ).pack(side=tk.RIGHT)

    def _on_url(self):
        self.url_frame.pack(fill=tk.X, pady=(0, 10), before=self.btn_row)
        self.entry_url.focus_set()

    def _hide_url_frame(self):
        self.url_frame.pack_forget()

    def _do_fetch_url(self):
        url = self.url_var.get().strip()
        if not url:
            return
        if not url.startswith(("http://", "https://")):
            messagebox.showwarning("URLエラー", "http:// または https:// で始まるURLを入力してください。", parent=self)
            return

        if not self.app.extractor:
            messagebox.showerror("エラー", "抽出DLLが読み込まれていません。", parent=self)
            return

        self.btn_fetch_submit.state(["disabled"])
        self.update_idletasks()

        def fetch_work():
            result = {}
            try:
                result["data"], result["jpeg"] = self.app.extractor.extract_url(url)
            except Exception as e:
                result["error"] = str(e)

            def finish():
                try:
                    self.btn_fetch_submit.state(["!disabled"])
                except Exception:
                    pass

                if "error" in result:
                    messagebox.showerror("URL取得エラー", f"URLからの情報取得に失敗しました:\n{result['error']}", parent=self)
                    return

                self.app.db.set_source_url(self.item_id, url)
                dlg = UrlResultDialog(
                    self, self.app.db, self.item_id, result["data"], result.get("jpeg"),
                    placeholder=self.app.extractor.placeholder_jpeg(),
                    on_applied=lambda: None
                )
                self.wait_window(dlg)

                if getattr(dlg, "applied", False):
                    self.action = "url"
                    self.apply_to_all = self.apply_all_var.get()
                    self.destroy()
                else:
                    self._hide_url_frame()

            self.after(0, finish)

        threading.Thread(target=fetch_work, daemon=True).start()

    def _on_manual(self):
        self.action = "manual"
        self.apply_to_all = self.apply_all_var.get()
        self.destroy()
        self.app.after(50, lambda: ItemDetailDialog(
            self.app, self.app.db, self.item_id,
            on_update_callback=self.app.refresh,
            extractor=self.app.extractor
        ))

    def _on_keep(self):
        self.action = "keep"
        self.apply_to_all = self.apply_all_var.get()
        self.destroy()

    def _on_cancel(self):
        self.action = "cancel"
        self.apply_to_all = False
        try:
            self.app.db.delete_item(self.item_id)
        except Exception:
            pass
        self.destroy()


class CatalogApp(tk.Tk):
    def __init__(self):
        super().__init__()
        apply_theme(self)
        self.title("グリモワールシェルフ")
        self.configure(background=C.BG)

        self.db = Database()
        self.db.normalize_tags()
        self.settings = load_app_settings(self.db)

        # 初回起動時はディスプレイ中央、2回目以降は前回位置を復元
        saved_geom = get_saved_geometry("main", 1200, 800)
        if saved_geom:
            self.geometry(saved_geom)
        else:
            center_on_screen(self, 1200, 800)

        # 最大化状態の復元
        if self.settings.get("window", "main_maximized") == "1":
            self.after(60, lambda: self.state("zoomed"))

        # ウィンドウ移動・終了時の位置保存
        self.protocol("WM_DELETE_WINDOW", self.on_exit)
        self._is_window_dragging = False
        self._geom_save_job = None
        self.bind("<Configure>", self._on_window_configure, add="+")

        # タイトルバーの色をアプリ本体と同化、ボタンも背景同化
        apply_window_titlebar_theme(self, borderless=True)
        self.after(60, lambda: apply_window_titlebar_theme(self, borderless=True))

        try:
            self.extractor = RustDllExtractor(RUST_ROOT)
        except Exception as e:
            self.extractor = None
            messagebox.showerror("DLL 読み込みエラー", str(e))

        self.records = []
        self.selected_id = None
        self.selected_tags = set()
        self.nav = "all"
        self.sort_var = tk.StringVar(value="added_desc")
        self.view_var = tk.StringVar(value="shelf")
        self.size_var = tk.StringVar(value="M")
        self.search_var = tk.StringVar()
        self.tag_popup = None

        self.setup_ui()
        self._setup_dnd()
        self.refresh()

    def _setup_dnd(self):
        """ドラッグ＆ドロップ (D&D) によるPDF/ZIPファイルの取り込みを有効化"""
        if windnd is None:
            return

        self.update_idletasks()
        targets = [
            self,
            getattr(self, "shelf", None),
            getattr(self, "content_frame", None),
            getattr(self, "side_frame", None)
        ]
        for t in targets:
            if t is not None:
                try:
                    windnd.hook_dropfiles(t, func=self._on_drop_files, force_unicode=True)
                except Exception as e:
                    pass

    def _on_drop_files(self, file_paths):
        """D&Dでドロップされたファイル・フォルダパスを受け取りインポートを実行"""
        if not file_paths:
            return
        self.after(20, lambda: self.import_files(file_paths))

    def _on_window_configure(self, event):
        if event.widget == self:
            if getattr(self, "_is_window_dragging", False):
                return
            if self._geom_save_job:
                self.after_cancel(self._geom_save_job)
            self._geom_save_job = self.after(500, self._auto_save_geometry)

    def _auto_save_geometry(self):
        self._geom_save_job = None
        save_geometry("main", self)

    def _on_global_click(self, event):
        """検索窓以外の場所をクリックした際、検索窓からフォーカスを外して点滅カーソルを消す。
        また、タグポップアップの枠外をクリックした際は内容を確定反映して閉じる。"""
        if hasattr(self, "tag_popup") and self.tag_popup and self.tag_popup.winfo_exists():
            try:
                is_inside = (event.widget == self.tag_popup or str(event.widget).startswith(str(self.tag_popup) + "."))
            except Exception:
                is_inside = False
            if not is_inside:
                self.tag_popup.close_and_apply()

        if hasattr(self, "entry_search") and event.widget != self.entry_search:
            self.focus_set()

    def on_exit(self):
        """アプリ終了時にウィンドウ位置とサイズをINIに記録"""
        if self._geom_save_job:
            self.after_cancel(self._geom_save_job)
        save_geometry("main", self)
        self.destroy()

    def setup_ui(self):
        # 1. Antigravity スタイルのカスタムタイトルバー（背景同化ボタン付き）
        self.titlebar = CustomTitleBar(self, self, title_text="グリモワールシェルフ")

        # 2. メインコンテナ（サイドバー＋コンテンツ領域）
        main_container = tk.Frame(self, background=C.BG)
        main_container.pack(fill=tk.BOTH, expand=True)

        # サイドバー
        self.side_frame = tk.Frame(main_container, background=C.SIDEBAR, width=220)
        self.side_frame.pack(side=tk.LEFT, fill=tk.Y)
        self.side_frame.pack_propagate(False)

        # 「グリモワールシェルフ」ラベルは削除し、「＋ シナリオを追加」を一番上に配置
        ttk.Button(self.side_frame, text="＋ シナリオを追加", style="Accent.TButton", command=self.on_add_entry).pack(
            fill=tk.X, padx=14, pady=(16, 6)
        )
        ttk.Button(self.side_frame, text="タグ管理", style="Side.TButton", command=lambda: TagEditorDialog(self, self.db, on_close_callback=self.refresh)).pack(fill=tk.X, padx=14, pady=4)
        ttk.Button(self.side_frame, text="Notion 設定", style="Side.TButton", command=lambda: NotionSettingsDialog(self, self.db)).pack(fill=tk.X, padx=14, pady=4)

        # コンテンツ領域
        self.content_frame = tk.Frame(main_container, background=C.BG)
        self.content_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        top = tk.Frame(self.content_frame, background=C.BG)
        top.pack(fill=tk.X, padx=20, pady=10)
        e = ttk.Entry(top, textvariable=self.search_var)
        e.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        self.entry_search = e
        self.search_var.trace_add("write", lambda *a: self.update_view())

        # 検索窓以外のどこをクリックしてもカーソルの点滅を消去する
        self.bind_all("<Button-1>", self._on_global_click, add="+")

        # 本棚とスクロールバーをまとめるコンテナ
        shelf_box = tk.Frame(self.content_frame, background=C.BG)
        shelf_box.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        self.scrollbar = ttk.Scrollbar(shelf_box, orient=tk.VERTICAL)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.shelf = ShelfView(shelf_box, self)
        self.shelf.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.shelf.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.configure(command=self.shelf.yview)

        # 下からスライドインする詳細情報パネル
        self.slide_panel = SlideDetailPanel(self.content_frame, self)

    def refresh(self):
        self.records = self.db.all_records()
        self.update_view()

    def update_view(self):
        kw = self.search_var.get().strip().lower()
        visible = [r for r in self.records if not kw or kw in (r["title"] or "").lower()]
        self.shelf.show(visible, self.view_var.get(), self.size_var.get(), self.selected_id)

    def select_item(self, item_id):
        self.selected_id = item_id
        if item_id:
            ItemDetailDialog(self, self.db, item_id, on_update_callback=self.refresh, extractor=self.extractor)

    def on_add_entry(self):
        chosen_files = filedialog.askopenfilenames(
            title="シナリオファイルを選択（複数選択可）",
            filetypes=[("シナリオファイル (PDF, ZIP)", "*.pdf;*.zip"), ("すべてのファイル", "*.*")]
        )
        if not chosen_files:
            return
        self.import_files(chosen_files)

    def import_files(self, paths):
        """PDF/ZIPファイルまたはフォルダを取り込んでシナリオとして登録する（1フォルダ=1シナリオ）"""
        targets = collect_scenario_targets(paths)
        if not targets:
            messagebox.showinfo(
                "お知らせ",
                "取り込み対象のシナリオが見つかりませんでした。\n"
                "（対応形式: シナリオフォルダ, .pdf, .zip）"
            )
            return

        if self.extractor is None:
            messagebox.showerror("エラー", "抽出DLLが読み込まれていません。")
            return

        total = len(targets)
        success_count = 0
        errors = []
        skip_incomplete_prompts = False

        progress = ImportProgressDialog(self, total) if total > 1 else None

        for idx, target_path in enumerate(targets, start=1):
            raw_name = os.path.basename(target_path.rstrip(r"\/"))
            if progress:
                if progress.is_cancelled:
                    break
                progress.update_progress(idx, total, raw_name)

            try:
                # フォルダ・ZIPの内部探索と情報の統合
                data = extract_scenario_data(self.extractor, target_path)
                fields = data["fields"]

                item_id = self.db.save_item(
                    target_path, data["title"], fields.get("system_name"), fields.get("players_text"),
                    fields.get("duration_text"), fields.get("overview"), fields.get("synopsis"),
                    data.get("thumb_bytes")
                )
                self.db.add_tags_to_item(item_id, set(data.get("tags") or []))

                # 不足項目がある場合、POPUP確認ダイアログを表示
                if data["missing_items"] and not skip_incomplete_prompts:
                    dlg = ScenarioIncompleteDialog(
                        self, self, data, item_id, is_multiple=(total > 1)
                    )
                    self.wait_window(dlg)

                    if dlg.action == "cancel":
                        # キャンセルボタンが押された場合：登録を中止し、DBから即座に削除
                        try:
                            self.db.delete_item(item_id)
                        except Exception:
                            pass
                        if progress:
                            progress.is_cancelled = True
                        break

                    if dlg.apply_to_all:
                        skip_incomplete_prompts = True

                success_count += 1
            except Exception as e:
                errors.append((raw_name, str(e)))

        if progress:
            progress.close()

        self.refresh()

        if total == 1:
            if success_count == 1:
                single_name = os.path.basename(targets[0].rstrip(r"\/"))
                single_title = os.path.splitext(single_name)[0] if os.path.isfile(targets[0]) else single_name
                messagebox.showinfo("登録完了", f"「{single_title}」を追加しました。", parent=self)
            elif not errors:
                # キャンセル時（登録中止）
                pass
            else:
                err_msg = errors[0][1] if errors else "不明なエラー"
                messagebox.showerror("エラー", f"取り込みに失敗しました:\n{err_msg}", parent=self)
        else:
            if progress and progress.is_cancelled:
                msg = f"{success_count} 件のシナリオを取り込みました（取り込みを中止しました）。"
                messagebox.showinfo("取り込み中止", msg, parent=self)
            elif errors:
                msg = f"{success_count} / {total} 件のシナリオを取り込みました。"
                err_details = "\n".join(f"・{name}: {err}" for name, err in errors[:5])
                if len(errors) > 5:
                    err_details += f"\n…他 {len(errors) - 5} 件"
                msg += f"\n\n【失敗した項目 ({len(errors)}件)】\n{err_details}"
                messagebox.showwarning("取り込み結果", msg, parent=self)
            else:
                msg = f"{success_count} / {total} 件のシナリオを取り込みました。"
                messagebox.showinfo("取り込み完了", msg, parent=self)


if __name__ == "__main__":
    app = CatalogApp()
    app.mainloop()