"""詳細画面（グリモワール調）に完全調和するメイン画面デザインプレビューの高精度生成スクリプト
"""

import os
import math
from PIL import Image, ImageDraw, ImageFont, ImageFilter

def draw_fleur(draw, cx, cy, size=18, color=(212, 178, 111, 255)):
    """西洋アンティーク調のフルール・ド・リス（百合紋章）をベクター描画"""
    S = size
    # 中央の花弁
    pts_center = [
        (cx, cy - S * 0.44),
        (cx + S * 0.12, cy - S * 0.10),
        (cx + S * 0.08, cy + S * 0.15),
        (cx, cy + S * 0.10),
        (cx - S * 0.08, cy + S * 0.15),
        (cx - S * 0.12, cy - S * 0.10),
    ]
    draw.polygon(pts_center, fill=color)

    # 左の花弁
    pts_left = [
        (cx - S * 0.06, cy + S * 0.05),
        (cx - S * 0.28, cy - S * 0.15),
        (cx - S * 0.40, cy - S * 0.02),
        (cx - S * 0.28, cy + S * 0.20),
        (cx - S * 0.06, cy + S * 0.14),
    ]
    draw.polygon(pts_left, fill=color)

    # 右の花弁
    pts_right = [
        (cx + S * 0.06, cy + S * 0.05),
        (cx + S * 0.28, cy - S * 0.15),
        (cx + S * 0.40, cy - S * 0.02),
        (cx + S * 0.28, cy + S * 0.20),
        (cx + S * 0.06, cy + S * 0.14),
    ]
    draw.polygon(pts_right, fill=color)

    # 根元の結束飾り
    pts_base = [
        (cx - S * 0.16, cy + S * 0.14),
        (cx + S * 0.16, cy + S * 0.14),
        (cx + S * 0.08, cy + S * 0.36),
        (cx, cy + S * 0.44),
        (cx - S * 0.08, cy + S * 0.36),
    ]
    draw.polygon(pts_base, fill=color)


def draw_corner_bracket(draw, x, y, size=18, orientation="NW", color=(140, 112, 62, 255)):
    """アンティークな四隅の真鍮ブラケット金具をベクター描画"""
    L = size
    w = 2
    if orientation == "NW":
        draw.line([(x, y + L), (x, y), (x + L, y)], fill=color, width=w)
        draw.ellipse([x - 2, y - 2, x + 4, y + 4], fill=color)
        draw.line([(x + 4, y + 4), (x + L - 4, y + 4)], fill=(74, 60, 32, 255), width=1)
        draw.line([(x + 4, y + 4), (x + 4, y + L - 4)], fill=(74, 60, 32, 255), width=1)
    elif orientation == "NE":
        draw.line([(x, y), (x + L, y), (x + L, y + L)], fill=color, width=w)
        draw.ellipse([x + L - 4, y - 2, x + L + 2, y + 4], fill=color)
        draw.line([(x + 4, y + 4), (x + L - 4, y + 4)], fill=(74, 60, 32, 255), width=1)
        draw.line([(x + L - 4, y + 4), (x + L - 4, y + L - 4)], fill=(74, 60, 32, 255), width=1)
    elif orientation == "SW":
        draw.line([(x, y), (x, y + L), (x + L, y + L)], fill=color, width=w)
        draw.ellipse([x - 2, y + L - 4, x + 4, y + L + 2], fill=color)
        draw.line([(x + 4, y + L - 4), (x + L - 4, y + L - 4)], fill=(74, 60, 32, 255), width=1)
        draw.line([(x + 4, y + 4), (x + 4, y + L - 4)], fill=(74, 60, 32, 255), width=1)
    elif orientation == "SE":
        draw.line([(x + L, y), (x + L, y + L), (x, y + L)], fill=color, width=w)
        draw.ellipse([x + L - 4, y + L - 4, x + L + 2, y + L + 2], fill=color)
        draw.line([(x + 4, y + L - 4), (x + L - 4, y + L - 4)], fill=(74, 60, 32, 255), width=1)
        draw.line([(x + L - 4, y + 4), (x + L - 4, y + L - 4)], fill=(74, 60, 32, 255), width=1)


def draw_divider_line(draw, x1, y1, x2, y2, color=(74, 60, 32, 255), accent_color=(212, 178, 111, 255)):
    """中央にダイヤオーナメントのある真鍮仕切り線"""
    draw.line([(x1, y1), (x2, y2)], fill=color, width=1)
    mid_x = (x1 + x2) // 2
    mid_y = (y1 + y2) // 2
    d = 4
    draw.polygon([(mid_x, mid_y - d), (mid_x + d, mid_y), (mid_x, mid_y + d), (mid_x - d, mid_y)], fill=accent_color)


def draw_search_icon(draw, cx, cy, size=14, color=(212, 178, 111, 255)):
    """虫眼鏡アイコンを描画"""
    r = size // 2 - 2
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=2)
    draw.line([(cx + r - 1, cy + r - 1), (cx + r + 4, cy + r + 4)], fill=color, width=2)


def render():
    src_path = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449\.user_uploaded\media_1792146845459_ff44e010.jpg"
    detail_img = Image.open(src_path).convert("RGBA")

    # 実表紙画像（共犯者）の切り出し
    cover_crop = detail_img.crop((50, 120, 324, 280))
    # 左下の羽ペン・懐中時計の透かし
    watermark_crop = detail_img.crop((30, 490, 340, 670))

    # キャンバスサイズ
    W, H = 1260, 800
    canvas = Image.new("RGBA", (W, H), (22, 18, 15, 255))
    draw = ImageDraw.Draw(canvas)

    # カラー定義
    C_BG = (22, 18, 15, 255)            # #16120f
    C_PANEL = (26, 21, 17, 255)         # #1a1511
    C_BRASS_LIGHT = (212, 178, 111, 255)# #d4b26f (金文字・アクセント)
    C_BRASS_BASE = (140, 112, 62, 255)  # #8c703e (真鍮枠線)
    C_BRASS_DARK = (74, 60, 32, 255)    # #4a3c20 (シャドウ真鍮)
    C_BRASS_MUTED = (48, 38, 22, 255)
    C_TEXT_WHITE = (235, 225, 208, 255) # 本文アイボリー
    C_TEXT_MUTED = (140, 125, 108, 255) # 補助セピア
    C_CARD_BG = (20, 16, 13, 255)

    # フォント
    font_path_mincho = "C:/Windows/Fonts/yumin.ttf"
    font_path_gothic = "C:/Windows/Fonts/meiryo.ttc"
    if not os.path.exists(font_path_mincho):
        font_path_mincho = "C:/Windows/Fonts/msmincho.ttc"
    if not os.path.exists(font_path_gothic):
        font_path_gothic = "C:/Windows/Fonts/msgothic.ttc"

    try:
        f_title = ImageFont.truetype(font_path_mincho, 17)
        f_head = ImageFont.truetype(font_path_mincho, 14)
        f_body = ImageFont.truetype(font_path_gothic, 12)
        f_small = ImageFont.truetype(font_path_gothic, 11)
        f_card_title = ImageFont.truetype(font_path_gothic, 12)
    except Exception:
        f_title = f_head = f_body = f_small = f_card_title = ImageFont.load_default()

    # 1. ビネット効果（周辺減光）
    vignette = Image.new("L", (W, H), 0)
    vdraw = ImageDraw.Draw(vignette)
    cx, cy = W // 2, H // 2
    max_r = math.sqrt(cx**2 + cy**2)
    for y in range(0, H, 5):
        for x in range(0, W, 5):
            dist = math.sqrt((x - cx)**2 + (y - cy)**2)
            val = int(min(255, (dist / max_r) * 120))
            vdraw.rectangle([x, y, x + 5, y + 5], fill=val)
    vignette = vignette.filter(ImageFilter.GaussianBlur(20))
    dark_overlay = Image.new("RGBA", (W, H), (10, 8, 7, 255))
    canvas.paste(dark_overlay, (0, 0), vignette)

    # 2. ウィンドウ外枠＆四隅真鍮金具
    draw.rectangle([6, 6, W - 7, H - 7], outline=C_BRASS_DARK, width=1)
    draw.rectangle([9, 9, W - 10, H - 10], outline=C_BRASS_BASE, width=1)
    draw.rectangle([11, 11, W - 12, H - 12], outline=C_BRASS_MUTED, width=1)

    draw_corner_bracket(draw, 10, 10, 20, "NW", C_BRASS_BASE)
    draw_corner_bracket(draw, W - 30, 10, 20, "NE", C_BRASS_BASE)
    draw_corner_bracket(draw, 10, H - 30, 20, "SW", C_BRASS_BASE)
    draw_corner_bracket(draw, W - 30, H - 30, 20, "SE", C_BRASS_BASE)

    # 3. タイトルバー＆ヘッダー
    draw_fleur(draw, 34, 34, 18, C_BRASS_LIGHT)
    draw.text((50, 24), "魔導書架  ―  TRPG Scenario Archive", font=f_title, fill=C_BRASS_LIGHT)

    # 検索バー
    sb_x, sb_y, sb_w, sb_h = 440, 20, 270, 30
    draw.rectangle([sb_x, sb_y, sb_x + sb_w, sb_y + sb_h], fill=(28, 23, 19, 255), outline=C_BRASS_BASE, width=1)
    draw_search_icon(draw, sb_x + 18, sb_y + 15, 14, C_BRASS_LIGHT)
    draw.text((sb_x + 36, sb_y + 7), "書名、システム、タグで検索...", font=f_small, fill=C_TEXT_MUTED)

    # ソート切り替え
    st_x, st_y, st_w, st_h = 725, 20, 145, 30
    draw.rectangle([st_x, st_y, st_x + st_w, st_y + st_h], fill=(28, 23, 19, 255), outline=C_BRASS_BASE, width=1)
    draw.text((st_x + 14, st_y + 7), "登録が新しい順", font=f_small, fill=C_TEXT_WHITE)
    draw.text((st_x + st_w - 20, st_y + 7), "▼", font=f_small, fill=C_BRASS_LIGHT)

    # 「＋ シナリオを追加」ボタン
    btn_x, btn_y, btn_w, btn_h = 885, 20, 145, 30
    draw.rectangle([btn_x, btn_y, btn_x + btn_w, btn_y + btn_h], fill=(36, 29, 23, 255), outline=C_BRASS_LIGHT, width=1)
    draw.text((btn_x + 18, btn_y + 6), "＋ シナリオを追加", font=f_body, fill=C_BRASS_LIGHT)

    # ウィンドウ操作ボタン
    draw.text((W - 100, 20), "―    □    ✕", font=f_small, fill=C_TEXT_MUTED)

    # ヘッダー仕切り線
    draw_divider_line(draw, 24, 62, W - 24, 62, C_BRASS_DARK, C_BRASS_LIGHT)

    # 4. 左側サイドバー（目録・分類棚）
    sb_left, sb_top, sb_right, sb_bottom = 24, 74, 260, 750
    draw.rectangle([sb_left, sb_top, sb_right, sb_bottom], fill=(24, 19, 16, 200), outline=C_BRASS_BASE, width=1)
    draw.rectangle([sb_left + 2, sb_top + 2, sb_right - 2, sb_bottom - 2], outline=C_BRASS_DARK, width=1)

    # サイドバーのコーナー金具
    draw_corner_bracket(draw, sb_left + 2, sb_top + 2, 14, "NW", C_BRASS_BASE)
    draw_corner_bracket(draw, sb_right - 16, sb_top + 2, 14, "NE", C_BRASS_BASE)
    draw_corner_bracket(draw, sb_left + 2, sb_bottom - 16, 14, "SW", C_BRASS_BASE)
    draw_corner_bracket(draw, sb_right - 16, sb_bottom - 16, 14, "SE", C_BRASS_BASE)

    # 4.1 システム分類
    draw_fleur(draw, sb_left + 22, sb_top + 24, 14, C_BRASS_LIGHT)
    draw.text((sb_left + 36, sb_top + 16), "システム分類", font=f_head, fill=C_BRASS_LIGHT)
    draw_divider_line(draw, sb_left + 14, sb_top + 38, sb_right - 14, sb_top + 38, C_BRASS_DARK, C_BRASS_BASE)

    systems = [
        ("すべて", "18", False),
        ("クトゥルフ神話TRPG", "9", True),
        ("マーダーミステリー", "5", False),
        ("エモクロアTRPG", "2", False),
        ("その他", "2", False),
    ]
    cur_y = sb_top + 50
    for sname, scnt, ssel in systems:
        if ssel:
            draw.rectangle([sb_left + 8, cur_y - 2, sb_right - 8, cur_y + 24], fill=(38, 30, 22, 255), outline=C_BRASS_LIGHT, width=1)
            draw.text((sb_left + 18, cur_y + 3), f"▶  {sname}", font=f_body, fill=C_BRASS_LIGHT)
            draw.text((sb_right - 32, cur_y + 3), scnt, font=f_small, fill=C_BRASS_LIGHT)
        else:
            draw.text((sb_left + 18, cur_y + 3), f"    {sname}", font=f_body, fill=C_TEXT_WHITE)
            draw.text((sb_right - 32, cur_y + 3), scnt, font=f_small, fill=C_TEXT_MUTED)
        cur_y += 30

    # 4.2 しおり・タグ
    cur_y += 10
    draw.text((sb_left + 20, cur_y), "🏷  しおり・タグ", font=f_head, fill=C_BRASS_LIGHT)
    cur_y += 22
    draw_divider_line(draw, sb_left + 14, cur_y, sb_right - 14, cur_y, C_BRASS_DARK, C_BRASS_BASE)
    cur_y += 14

    tags = [
        ("CoC", (27, 94, 32)),
        ("マダミス", (106, 27, 154)),
        ("GM可", (160, 120, 28)),
        ("未通過", (21, 101, 192)),
        ("通過済み", (158, 42, 43)),
        ("6PL", (74, 60, 32)),
    ]
    tx, ty = sb_left + 14, cur_y
    for tname, tcolor in tags:
        tw = len(tname) * 15 + 24
        if tx + tw > sb_right - 14:
            tx = sb_left + 14
            ty += 30
        draw.rounded_rectangle([tx, ty, tx + tw, ty + 22], radius=11, fill=(28, 22, 18, 255), outline=C_BRASS_DARK, width=1)
        draw.ellipse([tx + 6, ty + 7, tx + 14, ty + 15], fill=tcolor)
        draw.text((tx + 18, ty + 3), tname, font=f_small, fill=C_TEXT_WHITE)
        tx += tw + 6

    # 4.3 羽ペン・懐中時計の透かし
    wm_w, wm_h = 220, 140
    wm_res = watermark_crop.resize((wm_w, wm_h), Image.Resampling.LANCZOS)
    canvas.paste(wm_res, (sb_left + 8, sb_bottom - 150), wm_res if wm_res.mode == 'RGBA' else None)

    # 5. 右側メイン書架エリア
    mb_left, mb_top, mb_right, mb_bottom = 276, 74, W - 24, 750
    draw.rectangle([mb_left, mb_top, mb_right, mb_bottom], fill=(24, 19, 16, 220), outline=C_BRASS_BASE, width=1)
    draw.rectangle([mb_left + 3, mb_top + 3, mb_right - 3, mb_bottom - 3], outline=C_BRASS_DARK, width=1)

    draw_corner_bracket(draw, mb_left + 2, mb_top + 2, 22, "NW", C_BRASS_BASE)
    draw_corner_bracket(draw, mb_right - 24, mb_top + 2, 22, "NE", C_BRASS_BASE)
    draw_corner_bracket(draw, mb_left + 2, mb_bottom - 24, 22, "SW", C_BRASS_BASE)
    draw_corner_bracket(draw, mb_right - 24, mb_bottom - 24, 22, "SE", C_BRASS_BASE)

    # 見出し
    draw_fleur(draw, mb_left + 26, mb_top + 24, 16, C_BRASS_LIGHT)
    draw.text((mb_left + 42, mb_top + 16), "書架一覧  ―  クトゥルフ神話TRPG  (9 冊)", font=f_head, fill=C_BRASS_LIGHT)
    draw_divider_line(draw, mb_left + 380, mb_top + 26, mb_right - 24, mb_top + 26, C_BRASS_DARK, C_BRASS_BASE)

    # 6. 書架グリッド（シナリオカード一覧）
    # 列数: 4, 行数: 2
    cols = 4
    col_w = 232
    row_h = 320
    grid_x = mb_left + 18
    grid_y = mb_top + 50

    dummy_scenarios = [
        {"title": "共犯者", "system": "マーダーミステリー", "pl": "6人", "time": "4時間", "tag": "マダミス", "hover": True, "img": cover_crop},
        {"title": "海も枯れるまで", "system": "クトゥルフ神話TRPG", "pl": "2人", "time": "6〜8時間", "tag": "CoC", "hover": False, "img": None},
        {"title": "狂気山脈 〜邪神の山嶺〜", "system": "クトゥルフ神話TRPG", "pl": "3〜4人", "time": "5時間", "tag": "CoC", "hover": False, "img": None},
        {"title": "カタシロ", "system": "クトゥルフ神話TRPG", "pl": "1人", "time": "1時間", "tag": "CoC", "hover": False, "img": None},
        {"title": "誰がロックを殺すのか", "system": "クトゥルフ神話TRPG", "pl": "4人", "time": "4〜6時間", "tag": "CoC", "hover": False, "img": None},
        {"title": "新約・コウフク論", "system": "エモクロアTRPG", "pl": "2〜3人", "time": "3時間", "tag": "未通過", "hover": False, "img": None},
        {"title": "死刑囚は笑わない", "system": "マーダーミステリー", "pl": "5人", "time": "3.5時間", "tag": "マダミス", "hover": False, "img": None},
        {"title": "デモンズ・ライン", "system": "ソード・ワールド2.5", "pl": "3〜5人", "time": "4時間", "tag": "通過済み", "hover": False, "img": None},
    ]

    for idx, sc in enumerate(dummy_scenarios):
        r = idx // cols
        c = idx % cols
        cx = grid_x + c * col_w
        cy = grid_y + r * row_h
        cw, ch = 216, 305
        is_hover = sc["hover"]

        # カード外枠
        if is_hover:
            # ホバー演出: 金色に輝く二重真鍮枠＋微光
            draw.rectangle([cx - 2, cy - 2, cx + cw + 2, cy + ch + 2], fill=(36, 28, 20, 255), outline=C_BRASS_LIGHT, width=2)
            draw.rectangle([cx + 1, cy + 1, cx + cw - 1, cy + ch - 1], fill=(28, 22, 17, 255), outline=C_BRASS_LIGHT, width=1)
        else:
            draw.rectangle([cx, cy, cx + cw, cy + ch], fill=C_CARD_BG, outline=C_BRASS_BASE, width=1)
            draw.rectangle([cx + 2, cy + 2, cx + cw - 2, cy + ch - 2], outline=C_BRASS_DARK, width=1)

        # 表紙画像領域 (幅 196, 高さ 185)
        tx, ty, tw, th = cx + 10, cy + 10, 196, 185
        draw.rectangle([tx, ty, tx + tw, ty + th], fill=(16, 12, 10, 255), outline=C_BRASS_BASE if not is_hover else C_BRASS_LIGHT, width=1)

        if sc["img"] is not None:
            cover_scaled = sc["img"].resize((tw - 4, th - 4), Image.Resampling.LANCZOS)
            canvas.paste(cover_scaled, (tx + 2, ty + 2))
        else:
            # 洋書・魔導書調グラフィック
            draw.rectangle([tx + 4, ty + 4, tx + tw - 4, ty + th - 4], fill=(22, 17, 14, 255), outline=C_BRASS_DARK, width=1)
            # フルール・ド・リス紋章
            draw_fleur(draw, tx + tw // 2, ty + th // 2 - 10, 26, C_BRASS_BASE)
            # 飾り線
            draw_divider_line(draw, tx + 24, ty + th // 2 + 20, tx + tw - 24, ty + th // 2 + 20, C_BRASS_DARK, C_BRASS_BASE)
            # タイトル（中央揃え）
            t_short = sc["title"]
            if len(t_short) > 10:
                t_short = t_short[:9] + "…"
            draw.text((tx + 20, ty + th - 32), t_short, font=f_small, fill=C_BRASS_LIGHT)

        # 右上に虫眼鏡またはタグピル
        if is_hover:
            draw.rounded_rectangle([tx + tw - 26, ty + 6, tx + tw - 6, ty + 26], radius=4, fill=(36, 28, 20, 230), outline=C_BRASS_LIGHT, width=1)
            draw_search_icon(draw, tx + tw - 16, ty + 16, 12, C_BRASS_LIGHT)
        else:
            tcolor = (27, 94, 32) if sc["tag"] == "CoC" else (106, 27, 154) if sc["tag"] == "マダミス" else (158, 42, 43)
            draw.rounded_rectangle([tx + tw - 58, ty + 6, tx + tw - 6, ty + 22], radius=8, fill=(24, 18, 14, 240), outline=C_BRASS_DARK, width=1)
            draw.ellipse([tx + tw - 52, ty + 9, tx + tw - 46, ty + 15], fill=tcolor)
            draw.text((tx + tw - 42, ty + 5), sc["tag"], font=f_small, fill=C_TEXT_WHITE)

        # カード情報
        draw.text((cx + 12, cy + 204), sc["title"], font=f_card_title, fill=C_BRASS_LIGHT if is_hover else C_TEXT_WHITE)
        draw.text((cx + 12, cy + 225), sc["system"], font=f_small, fill=C_BRASS_LIGHT if is_hover else C_TEXT_MUTED)
        draw.text((cx + 12, cy + 245), f"人数: {sc['pl']}  │  時間: {sc['time']}", font=f_small, fill=C_TEXT_MUTED)

        # 下部真鍮ディバイダー
        draw.line([(cx + 12, cy + ch - 12), (cx + cw - 12, cy + ch - 12)], fill=C_BRASS_MUTED, width=1)

    # 7. 下部ステータスバー
    draw.line([(24, 762), (W - 24, 762)], fill=C_BRASS_DARK, width=1)
    draw.text((32, 772), "全 18 冊収蔵  │  選択中: 共犯者 (マーダーミステリー)  │  Rust FFI Engine: 正常稼働中", font=f_small, fill=C_TEXT_MUTED)
    draw.text((W - 270, 772), "📖  クリックで本を開く (詳細・あらすじ編集)", font=f_small, fill=C_BRASS_LIGHT)

    # 保存
    out_dir = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449"
    out_path = os.path.join(out_dir, "preview_main_grimoire_matched.png")
    canvas.save(out_path, format="PNG")
    print("Matched main design saved to:", out_path)

if __name__ == "__main__":
    render()
