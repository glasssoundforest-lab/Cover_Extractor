"""Rust GFX モジュール (rust_gfx.py)

Pillow に依存していた木目テクスチャ、ドロップシャドウ、ページめくり変形、
本棚パーツ、クラシックカバー等の画像処理ロジックを Rust (cover_extractor.dll) で高速実行する。
Rust DLL が利用できない場合は、互換性のために Pillow 実装へ安全にフォールバックします。
"""

import ctypes
import hashlib
import io
import math
import os
import random
import sys
import tkinter as tk
import tkinter.font as tkfont
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageTk

# ==============================================================================
# 0. キャッシュとヘルパー
# ==============================================================================

_ART = {}
_ART_LIMIT = 4000


def _cached(key, make):
    img = _ART.get(key)
    if img is None:
        if len(_ART) > _ART_LIMIT:
            _ART.clear()
        img = _ART[key] = make()
    return img


def _rgba(color, alpha=255):
    if isinstance(color, tuple):
        if len(color) == 3:
            return color + (alpha,)
        return color
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4)) + (alpha,)


def _hex_to_int(color_str):
    if not color_str:
        return 0
    return int(color_str.lstrip("#"), 16)


def _seed(text):
    return int(hashlib.md5((text or "").encode("utf-8")).hexdigest()[:8], 16)


# ==============================================================================
# 1. Rust DLL ロードと FFI 定義
# ==============================================================================

_LIB_GFX = None


def get_gfx_lib():
    global _LIB_GFX
    if _LIB_GFX is not None:
        return _LIB_GFX

    dll_name = "cover_extractor.dll" if sys.platform == "win32" else "libcover_extractor.so"
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = []
    if os.environ.get("COVER_EXTRACTOR_DLL"):
        candidates.append(os.environ["COVER_EXTRACTOR_DLL"])
    candidates.extend([
        os.path.join(base_dir, dll_name),
        os.path.join(base_dir, "target", "release", dll_name),
        os.path.join(base_dir, "target", "debug", dll_name),
    ])

    lib = None
    for p in candidates:
        if os.path.isfile(p):
            try:
                lib = ctypes.CDLL(p)
                break
            except Exception:
                pass
    if not lib:
        return None

    try:
        lib.gfx_free_buffer.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        lib.gfx_free_buffer.restype = None

        lib.gfx_generate_wood_texture.argtypes = [
            ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_float, ctypes.POINTER(ctypes.c_size_t)
        ]
        lib.gfx_generate_wood_texture.restype = ctypes.c_void_p

        lib.gfx_generate_shadow.argtypes = [
            ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_float, ctypes.c_float, ctypes.POINTER(ctypes.c_size_t)
        ]
        lib.gfx_generate_shadow.restype = ctypes.c_void_p

        lib.gfx_turning_page.argtypes = [
            ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_bool, ctypes.c_float,
            ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_size_t)
        ]
        lib.gfx_turning_page.restype = ctypes.c_void_p

        lib.gfx_generate_bay.argtypes = [
            ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.POINTER(ctypes.c_size_t)
        ]
        lib.gfx_generate_bay.restype = ctypes.c_void_p

        lib.gfx_generate_crown.argtypes = [
            ctypes.c_uint32, ctypes.POINTER(ctypes.c_size_t)
        ]
        lib.gfx_generate_crown.restype = ctypes.c_void_p

        lib.gfx_generate_book_cover.argtypes = [
            ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint64,
            ctypes.c_bool, ctypes.c_uint32, ctypes.POINTER(ctypes.c_size_t)
        ]
        lib.gfx_generate_book_cover.restype = ctypes.c_void_p

        lib.gfx_generate_index_card.argtypes = [
            ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.POINTER(ctypes.c_size_t)
        ]
        lib.gfx_generate_index_card.restype = ctypes.c_void_p

        lib.gfx_generate_pill.argtypes = [
            ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_bool,
            ctypes.c_uint32, ctypes.c_uint32, ctypes.c_bool, ctypes.POINTER(ctypes.c_size_t)
        ]
        lib.gfx_generate_pill.restype = ctypes.c_void_p

        lib.gfx_generate_plate.argtypes = [
            ctypes.c_uint32, ctypes.c_uint32, ctypes.POINTER(ctypes.c_size_t)
        ]
        lib.gfx_generate_plate.restype = ctypes.c_void_p

        lib.gfx_generate_ribbon.argtypes = [
            ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.POINTER(ctypes.c_size_t)
        ]
        lib.gfx_generate_ribbon.restype = ctypes.c_void_p

        lib.gfx_generate_page.argtypes = [
            ctypes.c_uint32, ctypes.c_uint32, ctypes.c_bool, ctypes.c_uint32, ctypes.POINTER(ctypes.c_size_t)
        ]
        lib.gfx_generate_page.restype = ctypes.c_void_p

        _LIB_GFX = lib
        return _LIB_GFX
    except Exception as e:
        print(f"[rust_gfx] DLL symbol load warning: {e}", file=sys.stderr)
        return None


def reload_gfx_lib():
    global _LIB_GFX
    _LIB_GFX = None
    return get_gfx_lib()


# 後方互換性のためのプロパティ
class _LibGfxProxy:
    def __bool__(self):
        return get_gfx_lib() is not None

    def __getattr__(self, name):
        lib = get_gfx_lib()
        if lib is None:
            raise AttributeError(f"Rust GFX library is not loaded, cannot access {name}")
        return getattr(lib, name)


LIB_GFX = _LibGfxProxy()


def _take_png_image(ptr, out_len):
    if not ptr:
        return None
    lib = get_gfx_lib()
    try:
        raw_bytes = ctypes.string_at(ptr, out_len.value)
        return Image.open(io.BytesIO(raw_bytes)).copy()
    finally:
        if lib:
            lib.gfx_free_buffer(ptr, out_len.value)


# ==============================================================================
# 2. Rust GFX 関数群 (フォールバック付き)
# ==============================================================================

BAY_BOARD = 40
BAY_SIDE = 26
CROWN_H = 30
CLOTH = [("#5a1f22", "#d4b06a"), ("#1f3a2c", "#d9bf7a"), ("#1e2a4a", "#cfb071"), ("#4a3320", "#e0c48a"),
         ("#3b1e3a", "#d6b77a"), ("#2c3a3e", "#d2b678")]

_PIL_FONT_PATH = []


def pil_font(size, serif=True):
    if not _PIL_FONT_PATH:
        win = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
        local = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts")
        names = ["yumindb.ttf", "yumin.ttf", "BIZ-UDMinchoM.ttc", "msmincho.ttc", "yugothb.ttc", "YuGothB.ttc", "meiryob.ttc", "meiryo.ttc"]
        paths = [os.path.join(d, n) for d in (win, local) for n in names] + [
            "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc", "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", "/System/Library/Fonts/ヒラギノ明朝 ProN.ttc"]
        _PIL_FONT_PATH.append(next((p for p in paths if os.path.exists(p)), None))
    path = _PIL_FONT_PATH[0]
    if not path:
        return None
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return None


def wood_texture(w, h, light, dark, vertical=True, seed=1, contrast=1.0):
    if LIB_GFX:
        try:
            out_len = ctypes.c_size_t()
            ptr = LIB_GFX.gfx_generate_wood_texture(w, h, seed, contrast, ctypes.byref(out_len))
            img = _take_png_image(ptr, out_len)
            if img:
                return img
        except Exception:
            pass

    # フォールバック
    rnd = random.Random(seed)
    across, along = (w, h) if vertical else (h, w)
    streak = Image.effect_noise((max(across, 1), max(along // 40, 2)), 70).resize((across, along), Image.BICUBIC)
    fine = Image.effect_noise((max(across, 1), max(along // 6, 2)), 40).resize((across, along), Image.BICUBIC)
    wave = Image.new("L", (across, 1))
    phase = rnd.random() * 6.28
    wave.putdata([round(128 + 60 * math.sin(phase + x / (7 + rnd.random() * 2)) * math.sin(x / 53 + phase)) for x in range(across)])
    wave = wave.resize((across, along))
    gray = ImageChops.add(ImageChops.multiply(streak, wave), fine, scale=1.6)
    gray = ImageOps.autocontrast(gray, cutoff=2)
    if contrast != 1.0:
        gray = gray.point(lambda v: max(0, min(255, round(128 + (v - 128) * contrast))))
    if not vertical:
        gray = gray.transpose(getattr(Image, "Transpose", Image).ROTATE_90).resize((w, h))
    return ImageOps.colorize(gray, black=dark, white=light).convert("RGBA")


def bay_photo(root, width, height, seed=0):
    def make():
        if LIB_GFX:
            try:
                out_len = ctypes.c_size_t()
                ptr = LIB_GFX.gfx_generate_bay(width, height, seed, ctypes.byref(out_len))
                img = _take_png_image(ptr, out_len)
                if img:
                    return ImageTk.PhotoImage(img, master=root)
            except Exception:
                pass

        # フォールバック
        im = wood_texture(width, height, "#3d2717", "#1f130a", vertical=True, seed=seed + 3, contrast=0.7)
        shade = Image.new("L", (width, height), 0)
        sd = ImageDraw.Draw(shade)
        for i in range(46):
            sd.line([(0, i), (width, i)], fill=round(190 * (1 - i / 46) ** 1.6))
        for i in range(40):
            v = round(150 * (1 - i / 40) ** 2)
            sd.line([(BAY_SIDE + i, 0), (BAY_SIDE + i, height)], fill=max(v, 0))
            sd.line([(width - BAY_SIDE - 1 - i, 0), (width - BAY_SIDE - 1 - i, height)], fill=max(v, 0))
        dark = Image.new("RGBA", (width, height), (8, 4, 2, 255))
        dark.putalpha(ImageChops.lighter(shade, Image.new("L", (width, height), 30)))
        im = Image.alpha_composite(im, dark)
        for x0 in (0, width - BAY_SIDE):
            post = wood_texture(BAY_SIDE, height, "#6a4527", "#3a2413", vertical=True, seed=seed + x0 + 11, contrast=0.9)
            pd = ImageDraw.Draw(post)
            pd.line([(1, 0), (1, height)], fill=_rgba("#8a603a"))
            pd.line([(BAY_SIDE - 2, 0), (BAY_SIDE - 2, height)], fill=_rgba("#24150a"))
            im.alpha_composite(post, (x0, 0))
        top = height - BAY_BOARD
        top_face = wood_texture(width - 2 * BAY_SIDE + 8, 8, "#7d5431", "#5a391f", vertical=False, seed=seed + 5)
        im.alpha_composite(top_face, (BAY_SIDE - 4, top))
        front = wood_texture(width - 2, BAY_BOARD - 8, "#6e4728", "#3f2714", vertical=False, seed=seed + 7, contrast=1.1)
        fd = ImageDraw.Draw(front)
        fd.line([(0, 0), (width, 0)], fill=_rgba("#9a6c42"))
        fd.line([(0, 1), (width, 1)], fill=_rgba("#87603b"))
        fd.line([(0, BAY_BOARD - 9), (width, BAY_BOARD - 9)], fill=_rgba("#1c1007"))
        im.alpha_composite(front, (1, top + 8))
        return ImageTk.PhotoImage(im, master=root)

    return _cached(("bay", width, height, seed), make)


def crown_photo(root, width):
    def make():
        if LIB_GFX:
            try:
                out_len = ctypes.c_size_t()
                ptr = LIB_GFX.gfx_generate_crown(width, ctypes.byref(out_len))
                img = _take_png_image(ptr, out_len)
                if img:
                    return ImageTk.PhotoImage(img, master=root)
            except Exception:
                pass

        # フォールバック
        h = CROWN_H
        im = wood_texture(width, h, "#7a5030", "#402714", vertical=False, seed=21)
        d = ImageDraw.Draw(im)
        d.line([(0, 0), (width, 0)], fill=_rgba("#a37548"))
        d.line([(0, 9), (width, 9)], fill=_rgba("#2a1809"))
        d.line([(0, 10), (width, 10)], fill=_rgba("#8f653d"))
        d.line([(0, h - 6), (width, h - 6)], fill=_rgba("#2a1809"))
        d.line([(0, h - 5), (width, h - 5)], fill=_rgba("#8f653d"))
        d.line([(0, h - 1), (width, h - 1)], fill=_rgba("#1a0f06"))
        return ImageTk.PhotoImage(im, master=root)

    return _cached(("crown", width), make)


def _rounded_mask(w, h, radius, k=4):
    m = Image.new("L", (w * k, h * k), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w * k - 1, h * k - 1], radius=radius * k, fill=255)
    return m.resize((w, h), Image.LANCZOS)


def classic_cover(title, w, h):
    seed = _seed(title)
    cloth, gold = CLOTH[seed % len(CLOTH)]
    im = Image.new("RGBA", (w, h), _rgba(cloth))
    grain = Image.effect_noise((w, h), 24).convert("L")
    tex = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    tex.putalpha(grain.point(lambda v: max(0, min(70, (v - 110) // 2))))
    im = Image.alpha_composite(im, tex)
    vig = Image.new("L", (w, h), 0)
    ImageDraw.Draw(vig).rectangle([w * 0.08, h * 0.06, w * 0.92, h * 0.94], fill=255)
    vig = vig.filter(ImageFilter.GaussianBlur(min(w, h) * 0.12))
    darkened = Image.alpha_composite(im, Image.new("RGBA", (w, h), (0, 0, 0, 120)))
    im = Image.composite(im, darkened, vig)
    k = 3
    layer = Image.new("RGBA", (w * k, h * k), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    g = _rgba(gold, 235)
    lw = max(k, round(w * k / 110))
    m1, m2 = w * k * 0.09, w * k * 0.13
    d.rectangle([m1, m1, w * k - m1, h * k - m1], outline=g, width=lw)
    d.rectangle([m2, m2, w * k - m2, h * k - m2], outline=_rgba(gold, 170), width=max(1, lw // 2))
    for cx, cy in ((m2, m2), (w * k - m2, m2), (m2, h * k - m2), (w * k - m2, h * k - m2)):
        r = w * k * 0.03
        d.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)], fill=g)
    cx, cy, r = w * k / 2, h * k * 0.66, w * k * 0.13
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=g, width=lw)
    layer = layer.resize((w, h), Image.LANCZOS)
    im = Image.alpha_composite(im, layer)
    font = pil_font(max(9, round(w / 8.5)))
    if font and title:
        d = ImageDraw.Draw(im)
        max_w = w * 0.68
        lines, cur = [], ""
        for ch in title:
            if d.textlength(cur + ch, font=font) > max_w and cur:
                lines.append(cur)
                cur = ch
                if len(lines) == 3:
                    break
            else:
                cur += ch
        if cur and len(lines) < 3:
            lines.append(cur)
        size = font.size
        y = h * 0.2
        for line in lines:
            tw = d.textlength(line, font=font)
            d.text(((w - tw) / 2 + 1, y + 1), line, font=font, fill=(0, 0, 0, 120))
            d.text(((w - tw) / 2, y), line, font=font, fill=_rgba(gold))
            y += size * 1.25
    return im.convert("RGB")


def _fit_cover(thumb, title, w, h):
    if thumb:
        try:
            src = Image.open(io.BytesIO(thumb)).convert("RGB")
            return ImageOps.fit(src, (w, h), Image.LANCZOS, centering=(0.5, 0.3))
        except Exception:
            pass
    return classic_cover(title, w, h)


def _binding(im):
    w, h = im.size
    band = max(4, round(w * 0.06))
    sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(sh)
    for i in range(band):
        d.line([(i, 0), (i, h)], fill=(0, 0, 0, round(120 * (1 - i / band))))
    d.line([(band, 0), (band, h)], fill=(255, 255, 255, 34))
    d.line([(band + 1, 0), (band + 1, h)], fill=(0, 0, 0, 40))
    for y in range(h // 3):
        d.line([(0, y), (w, y)], fill=(255, 236, 200, round(20 * (1 - y / (h / 3)))))
    return Image.alpha_composite(im, sh)


def book_photo(root, key, thumb, title, w, h, shaded=False, radius=3, binding=True):
    def make():
        if LIB_GFX and not title:
            try:
                out_len = ctypes.c_size_t()
                t_bytes = thumb if thumb else b""
                seed_val = _seed(key or "")
                ptr = LIB_GFX.gfx_generate_book_cover(
                    t_bytes, len(t_bytes), w, h, seed_val, binding, radius, ctypes.byref(out_len)
                )
                img = _take_png_image(ptr, out_len)
                if img:
                    if shaded:
                        img = Image.alpha_composite(img, _vertical_shade(w, h, [(0, 0.0), (0.55, 0.0), (1, 0.9)]))
                    return ImageTk.PhotoImage(img, master=root)
            except Exception:
                pass

        # フォールバック (タイトル描画が必要な場合含む)
        im = _fit_cover(thumb, title, w, h).convert("RGBA")
        if binding:
            im = _binding(im)
        if shaded:
            im = Image.alpha_composite(im, _vertical_shade(w, h, [(0, 0.0), (0.55, 0.0), (1, 0.9)]))
        edge = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(edge).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, outline=(0, 0, 0, 110), width=1)
        im = Image.alpha_composite(im, edge)
        im.putalpha(_rounded_mask(w, h, radius))
        return ImageTk.PhotoImage(im, master=root)

    return _cached(("book", key, w, h, shaded, binding), make)


def cover_image(thumb, title, w, h):
    return _binding(_fit_cover(thumb, title, w, h).convert("RGBA"))


def _vertical_shade(w, h, stops):
    col = Image.new("L", (1, h))
    for y in range(h):
        r = y / max(h - 1, 1)
        v = 0.0
        for (p0, a0), (p1, a1) in zip(stops, stops[1:]):
            if p0 <= r <= p1:
                v = a0 + (a1 - a0) * ((r - p0) / (p1 - p0) if p1 > p0 else 0)
                break
        col.putpixel((0, y), round(255 * v))
    shade = Image.new("RGBA", (w, h), (8, 5, 3, 255))
    shade.putalpha(col.resize((w, h)))
    return shade


def shade_band_photo(root, w, h):
    def make():
        return ImageTk.PhotoImage(_vertical_shade(w, h, [(0, 0.0), (0.35, 0.55), (1, 0.92)]), master=root)
    return _cached(("band", w, h), make)


def book_shadow_photo(root, w, h, strength=0.75):
    def make():
        if LIB_GFX:
            try:
                pad = 14
                out_len = ctypes.c_size_t()
                ptr = LIB_GFX.gfx_generate_shadow(w, h, pad, 7.0, strength, ctypes.byref(out_len))
                img = _take_png_image(ptr, out_len)
                if img:
                    return ImageTk.PhotoImage(img, master=root)
            except Exception:
                pass

        pad = 14
        im = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
        ImageDraw.Draw(im).rectangle([pad, pad, pad + w, pad + h], fill=(0, 0, 0, round(255 * strength)))
        return ImageTk.PhotoImage(im.filter(ImageFilter.GaussianBlur(7)), master=root)

    return _cached(("bshadow", w, h, strength), make)


def ribbon_photo(root, w, h, color):
    def make():
        if LIB_GFX:
            try:
                out_len = ctypes.c_size_t()
                c_int = _hex_to_int(color)
                ptr = LIB_GFX.gfx_generate_ribbon(w, h, c_int, ctypes.byref(out_len))
                img = _take_png_image(ptr, out_len)
                if img:
                    return ImageTk.PhotoImage(img, master=root)
            except Exception:
                pass

        k = 4
        im = Image.new("RGBA", (w * k, h * k), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        notch = h * k * 0.82
        d.polygon([(0, 0), (w * k, 0), (w * k, h * k), (w * k / 2, notch), (0, h * k)], fill=_rgba(color))
        return ImageTk.PhotoImage(im.resize((w, h), Image.LANCZOS), master=root)

    return _cached(("ribbon", w, h, color), make)


def plate_photo(root, w, h):
    def make():
        if LIB_GFX:
            try:
                out_len = ctypes.c_size_t()
                ptr = LIB_GFX.gfx_generate_plate(w, h, ctypes.byref(out_len))
                img = _take_png_image(ptr, out_len)
                if img:
                    return ImageTk.PhotoImage(img, master=root)
            except Exception:
                pass

        k = 3
        im = Image.new("RGBA", (w * k, h * k), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle([0, 0, w * k - 1, h * k - 1], radius=2 * k, fill=_rgba("#b08a3e"), outline=_rgba("#6e5221"), width=k)
        d.rounded_rectangle([2 * k, 2 * k, w * k - 2 * k - 1, h * k - 2 * k - 1], radius=k, fill=_rgba("#efe3c4"))
        return ImageTk.PhotoImage(im.resize((w, h), Image.LANCZOS), master=root)

    return _cached(("plate", w, h), make)


def index_card_photo(root, w, h, paper_color="#f1e8d2"):
    def make():
        if LIB_GFX:
            try:
                out_len = ctypes.c_size_t()
                c_int = _hex_to_int(paper_color)
                ptr = LIB_GFX.gfx_generate_index_card(w, h, c_int, ctypes.byref(out_len))
                img = _take_png_image(ptr, out_len)
                if img:
                    return ImageTk.PhotoImage(img, master=root)
            except Exception:
                pass

        k = 2
        W, H = w + 12, h + 12
        im = Image.new("RGBA", (W * k, H * k), (0, 0, 0, 0))
        sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle([6 * k, 9 * k, (w + 6) * k, (h + 8) * k], radius=4 * k, fill=(0, 0, 0, 150))
        im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(4 * k)))
        card = Image.new("RGBA", (w * k, h * k), _rgba(paper_color))
        d = ImageDraw.Draw(card)
        for y in range(round(54 * k), h * k, round(19 * k)):
            d.line([(14 * k, y), (w * k - 14 * k, y)], fill=_rgba("#b9c4cf"), width=1)
        d.line([(14 * k, round(44 * k)), (w * k - 14 * k, round(44 * k))], fill=_rgba("#b9524a"), width=k)
        card.putalpha(_rounded_mask(w * k, h * k, 4 * k, k=1))
        im.alpha_composite(card, (6 * k, 4 * k))
        return ImageTk.PhotoImage(im.resize((W, H), Image.LANCZOS), master=root)

    return _cached(("icard", w, h, paper_color), make)


def page_image(w, h, side, paper_color="#f1e8d2"):
    if LIB_GFX:
        try:
            out_len = ctypes.c_size_t()
            c_int = _hex_to_int(paper_color)
            ptr = LIB_GFX.gfx_generate_page(w, h, side == "left", c_int, ctypes.byref(out_len))
            img = _take_png_image(ptr, out_len)
            if img:
                return img
        except Exception:
            pass

    im = Image.new("RGBA", (w, h), _rgba(paper_color))
    sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(sh)
    band = round(w * 0.12)
    for i in range(band):
        a = round(95 * (1 - i / band) ** 2)
        x = w - 1 - i if side == "left" else i
        d.line([(x, 0), (x, h)], fill=(60, 40, 15, a))
    return Image.alpha_composite(im, sh)


def leather_desk(w, h):
    return Image.new("RGBA", (w, h), _rgba("#241811"))


def _perspective_coeffs(src, dst):
    m, b = [], []
    for (x, y), (u, v) in zip(dst, src):
        m.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); b.append(u)
        m.append([0, 0, 0, x, y, 1, -v * x, -v * y]); b.append(v)
    n = 8
    a = [row[:] + [b[i]] for i, row in enumerate(m)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(a[r][col]))
        a[col], a[piv] = a[piv], a[col]
        if abs(a[col][col]) < 1e-12:
            return None
        for r in range(n):
            if r != col:
                f = a[r][col] / a[col][col]
                for c in range(col, n + 1):
                    a[r][c] -= f * a[col][c]
    return [a[i][n] / a[i][i] for i in range(n)]


def turning_page(img, width, height, spine_x_is_left, lift=0.07, darkness=0.0):
    if LIB_GFX:
        try:
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            input_bytes = buf.getvalue()

            out_grow = ctypes.c_uint32()
            out_len = ctypes.c_size_t()
            ptr = LIB_GFX.gfx_turning_page(
                input_bytes, len(input_bytes), int(width), int(height), spine_x_is_left, lift,
                ctypes.byref(out_grow), ctypes.byref(out_len)
            )
            out_img = _take_png_image(ptr, out_len)
            if out_img:
                return out_img, out_grow.value
        except Exception:
            pass

    # フォールバック
    w0, h0 = img.size
    width = max(1, int(width))
    grow = round(height * lift)
    H = height + 2 * grow
    if spine_x_is_left:
        dst = [(0, grow), (width, 0), (width, H), (0, grow + height)]
    else:
        dst = [(0, 0), (width, grow), (width, grow + height), (0, H)]
    src = [(0, 0), (w0, 0), (w0, h0), (0, h0)]
    coeffs = _perspective_coeffs(src, dst)
    if coeffs is None:
        return Image.new("RGBA", (width, H), (0, 0, 0, 0)), grow
    out = img.transform((width, H), getattr(Image, "Transform", Image).PERSPECTIVE, coeffs,
                        getattr(Image, "Resampling", Image).BILINEAR)
    mask = Image.new("L", (width, H), 0)
    ImageDraw.Draw(mask).polygon(dst, fill=255)
    if darkness > 0:
        out = Image.alpha_composite(out.convert("RGBA"), Image.new("RGBA", out.size, (10, 6, 3, round(255 * darkness))))
    out = out.convert("RGBA")
    out.putalpha(ImageChops.multiply(out.getchannel("A"), mask))
    return out, grow


def pill_photo(root, w, h, fill, outline, glow=None):
    def make():
        if LIB_GFX:
            try:
                out_len = ctypes.c_size_t()
                f_hex = _hex_to_int(fill)
                o_hex = _hex_to_int(outline)
                g_hex = _hex_to_int(glow) if glow else 0
                ptr = LIB_GFX.gfx_generate_pill(
                    w, h, f_hex, bool(fill), o_hex, g_hex, bool(glow), ctypes.byref(out_len)
                )
                img = _take_png_image(ptr, out_len)
                if img:
                    return ImageTk.PhotoImage(img, master=root)
            except Exception:
                pass

        g = 6 if glow else 1
        k = 4
        W, H = w + 2 * g, h + 2 * g
        im = Image.new("RGBA", (W * k, H * k), (0, 0, 0, 0))
        box = [g * k, g * k, (g + w) * k - 1, (g + h) * k - 1]
        if glow:
            gl = Image.new("RGBA", im.size, (0, 0, 0, 0))
            ImageDraw.Draw(gl).rounded_rectangle(box, radius=h * k // 2, outline=_rgba(glow, 200), width=3 * k)
            im = Image.alpha_composite(im, gl.filter(ImageFilter.GaussianBlur(3 * k)))
        ImageDraw.Draw(im).rounded_rectangle(box, radius=h * k // 2, fill=_rgba(fill) if fill else None,
                                             outline=_rgba(outline), width=round(1.5 * k))
        return ImageTk.PhotoImage(im.resize((W, H), Image.LANCZOS), master=root)

    return _cached(("pill", w, h, fill, outline, glow), make)


def pill_label(parent, text, bg, fg, fill, outline, glow=None, font=None, pad_x=12, height=None, **kw):
    font = font or "AppSmall"
    f = tkfont.nametofont(font, parent)
    w = f.measure(text) + pad_x * 2
    h = height or f.metrics("linespace") + 8
    img = pill_photo(parent, w, h, fill, outline, glow)
    lbl = tk.Label(parent, text=text, image=img, compound="center", background=bg, foreground=fg, font=font,
                   borderwidth=0, highlightthickness=0, **kw)
    lbl.image = img
    return lbl


def glow_photo(root, w, h, color, spread=16, strength=1.0, radius=8):
    def make():
        W, H = w + 2 * spread, h + 2 * spread
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(im).rounded_rectangle([spread, spread, spread + w, spread + h], radius=radius,
                                             fill=_rgba(color, round(255 * strength)))
        return ImageTk.PhotoImage(im.filter(ImageFilter.GaussianBlur(spread / 2.2)), master=root)
    return _cached(("glow", w, h, color, spread, strength, radius), make)


def ornament_photo(root, w, color):
    def make():
        k = 4
        h = 9
        im = Image.new("RGBA", (w * k, h * k), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        c = _rgba(color)
        cy = h * k / 2
        d.line([(0, cy), (w * k / 2 - 9 * k, cy)], fill=c, width=k)
        d.line([(w * k / 2 + 9 * k, cy), (w * k, cy)], fill=c, width=k)
        return ImageTk.PhotoImage(im.resize((w, h), Image.LANCZOS), master=root)
    return _cached(("orn", w, color), make)


def icon_photo(root, kind, color, size=20):
    def make():
        k = 4
        S = size * k
        im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        c = _rgba(color)
        lw = round(1.7 * k)
        if kind == "books":
            for i, yy in enumerate((0.58, 0.40, 0.22)):
                pts = [(S * 0.5, S * (yy - 0.14)), (S * 0.92, S * yy), (S * 0.5, S * (yy + 0.14)), (S * 0.08, S * yy)]
                if i == 2:
                    d.polygon(pts, fill=c)
                else:
                    d.line(pts + [pts[0]], fill=c, width=lw, joint="curve")
        elif kind == "star":
            pts = []
            for i in range(10):
                r = S * (0.46 if i % 2 == 0 else 0.2)
                a = -math.pi / 2 + i * math.pi / 5
                pts.append((S / 2 + r * math.cos(a), S * 0.53 + r * math.sin(a)))
            d.polygon(pts, fill=c)
        elif kind == "search":
            d.ellipse([S * 0.12, S * 0.12, S * 0.66, S * 0.66], outline=c, width=lw)
            d.line([(S * 0.6, S * 0.6), (S * 0.88, S * 0.88)], fill=c, width=round(lw * 1.3))
        return ImageTk.PhotoImage(im.resize((size, size), Image.LANCZOS), master=root)
    return _cached(("icon", kind, color, size), make)


_INDICATOR_IMAGES = {}


def _indicator_image(root, kind, size, fill, border, mark=None, gap=0):
    key = (kind, size, fill, border, mark, gap)
    if key in _INDICATOR_IMAGES:
        return _INDICATOR_IMAGES[key]
    k = 4
    big = size * k
    im = Image.new("RGBA", (big + gap * k, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    line = max(k, round(big / 14))
    box = [k, k, big - k - 1, big - k - 1]
    if kind == "check":
        d.rounded_rectangle(box, radius=big // 5, fill=_rgba(fill), outline=_rgba(border), width=line)
        if mark:
            pts = [(big * 0.28, big * 0.52), (big * 0.44, big * 0.67), (big * 0.73, big * 0.36)]
            d.line(pts, fill=_rgba(mark), width=round(big / 8), joint="curve")
    elif kind == "radio":
        d.ellipse(box, fill=_rgba(fill), outline=_rgba(border), width=line)
        if mark:
            r = big * 0.19
            c = big / 2
            d.ellipse([c - r, c - r, c + r, c + r], fill=_rgba(mark))
    elif kind == "chevron":
        w = round(big / 9)
        pts = [(big * 0.28, big * 0.40), (big * 0.50, big * 0.62), (big * 0.72, big * 0.40)]
        d.line(pts, fill=_rgba(fill), width=w, joint="curve")
    im = im.resize((size + gap, size), Image.LANCZOS)
    photo = ImageTk.PhotoImage(im, master=root)
    _INDICATOR_IMAGES[key] = photo
    return photo
