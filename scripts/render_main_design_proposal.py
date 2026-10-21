"""本を開いた画面（グリモワール調詳細画面）に完全調和する
メイン画面（書架ライブラリ）のデザイン案プレビュー画像を生成するスクリプト
"""

import os
import math
from PIL import Image, ImageDraw, ImageFont, ImageFilter

def create_preview():
    src_path = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449\.user_uploaded\media_1792146845459_ff44e010.jpg"
    detail_img = Image.open(src_path).convert("RGBA")
    dw, dh = detail_img.size

    # キャンバスサイズ (1280 x 820)
    W, H = 1280, 820
    canvas = Image.new("RGBA", (W, H), (19, 16, 14, 255))
    draw = ImageDraw.Draw(canvas)

    # カラー定義（詳細画像から正確に抽出）
    C_BG = (19, 16, 14, 255)
    C_PANEL = (25, 21, 18, 255)
    C_BRASS_LIGHT = (212, 178, 111, 255)  # #d4b26f (金文字・ハイライト)
    C_BRASS_BASE = (140, 112, 62, 255)    # #8c703e (真鍮枠)
    C_BRASS_DARK = (74, 60, 32, 255)      # #4a3c20 (暗い真鍮線)
    C_BRASS_MUTED = (45, 36, 22, 255)
    C_TEXT_WHITE = (237, 227, 210, 255)  # 本文アイボリー
    C_TEXT_MUTED = (140, 125, 108, 255)  # 補助セピア
    C_CARD_BG = (22, 18, 15, 255)

    # フォント設定
    font_path_mincho = "C:/Windows/Fonts/yumin.ttf"
    font_path_gothic = "C:/Windows/Fonts/meiryo.ttc"
    if not os.path.exists(font_path_mincho):
        font_path_mincho = "C:/Windows/Fonts/msmincho.ttc"
    if not os.path.exists(font_path_gothic):
        font_path_gothic = "C:/Windows/Fonts/msgothic.ttc"

    try:
        f_title = ImageFont.truetype(font_path_mincho, 18)
        f_head = ImageFont.truetype(font_path_mincho, 15)
        f_body = ImageFont.truetype(font_path_gothic, 13)
        f_small = ImageFont.truetype(font_path_gothic, 11)
        f_card_title = ImageFont.truetype(font_path_gothic, 13)
    except Exception:
        f_title = f_head = f_body = f_small = f_card_title = ImageFont.load_default()

    # 詳細画像から再利用パーツを切り出し
    # 1. コーナー金具（右側フレームの左上コーナー）
    # detail_img で右側フレームの角は約 x: 365, y: 45 付近
    corner_nw = detail_img.crop((360, 40, 385, 65))
    corner_ne = detail_img.crop((975, 40, 1000, 65))
    corner_sw = detail_img.crop((360, 630, 385, 655))
    corner_se = detail_img.crop((975, 630, 1000, 655))

    # 2. 表紙画像（共犯者）
    cover_crop = detail_img.crop((48, 118, 326, 408))

    # 3. 左下の羽ペン・懐中時計・筆記体カリグラフィの透かし
    watermark_crop = detail_img.crop((30, 480, 340, 670))

    # 4. アヤメ紋章（基本情報の左にあるフルール・ド・リス）
    fleur_crop = detail_img.crop((372, 57, 396, 80))

    # =========================================================================
    # 1. 背景のグラデーション・ビネット（周辺減光）
    # =========================================================================
    vignette = Image.new("L", (W, H), 0)
    vdraw = ImageDraw.Draw(vignette)
    cx, cy = W // 2, H // 2
    max_r = math.sqrt(cx**2 + cy**2)
    for y in range(0, H, 4):
        for x in range(0, W, 4):
            dist = math.sqrt((x - cx)**2 + (y - cy)**2)
            val = int(min(255, (dist / max_r) * 110))
            vdraw.rectangle([x, y, x + 4, y + 4], fill=val)
    vignette = vignette.filter(ImageFilter.GaussianBlur(16))
    
    # ビネットをブレンド
    dark_overlay = Image.new("RGBA", (W, H), (10, 8, 7, 255))
    canvas.paste(dark_overlay, (0, 0), vignette)

    # =========================================================================
    # 2. ウィンドウ外枠と四隅の真鍮ブラケット
    # =========================================================================
    draw.rectangle([6, 6, W - 7, H - 7], outline=C_BRASS_DARK, width=1)
    draw.rectangle([9, 9, W - 10, H - 10], outline=(100, 80, 45, 255), width=1)
    draw.rectangle([11, 11, W - 12, H - 12], outline=C_BRASS_MUTED, width=1)

    # 四隅にコーナー金具を配置
    canvas.paste(corner_nw, (8, 8), corner_nw if corner_nw.mode == 'RGBA' else None)
    canvas.paste(corner_ne, (W - 33, 8), corner_ne if corner_ne.mode == 'RGBA' else None)
    canvas.paste(corner_sw, (8, H - 33), corner_sw if corner_sw.mode == 'RGBA' else None)
    canvas.paste(corner_se, (W - 33, H - 33), corner_se if corner_se.mode == 'RGBA' else None)

    # =========================================================================
    # 3. タイトルバー＆ヘッダー操作部 (y: 12 〜 68)
    # =========================================================================
    # 羽ペン＆アプリタイトル
    draw.text((28, 22), "🪶 魔導書架 - TRPG Scenario Archive", font=f_title, fill=C_BRASS_LIGHT)

    # 検索バー (x: 440, y: 20, w: 280, h: 32) - 詳細画面のURL欄と同じ
    sb_x, sb_y, sb_w, sb_h = 440, 20, 280, 32
    draw.rectangle([sb_x, sb_y, sb_x + sb_w, sb_y + sb_h], fill=(28, 23, 20, 255), outline=C_BRASS_BASE, width=1)
    draw.text((sb_x + 10, sb_y + 8), "🔍", font=f_small, fill=C_BRASS_LIGHT)
    draw.text((sb_x + 32, sb_y + 8), "書名、システム、タグで検索...", font=f_small, fill=C_TEXT_MUTED)

    # ソート切り替え (x: 735, y: 20, w: 150, h: 32)
    st_x, st_y, st_w, st_h = 735, 20, 150, 32
    draw.rectangle([st_x, st_y, st_x + st_w, st_y + st_h], fill=(28, 23, 20, 255), outline=C_BRASS_BASE, width=1)
    draw.text((st_x + 12, st_y + 8), "登録が新しい順", font=f_small, fill=C_TEXT_WHITE)
    draw.text((st_x + st_w - 20, st_y + 8), "▼", font=f_small, fill=C_BRASS_LIGHT)

    # 「＋ シナリオを追加」ボタン (x: 900, y: 20, w: 145, h: 32) - 詳細画面の編集ボタンと同じ
    btn_x, btn_y, btn_w, btn_h = 900, 20, 145, 32
    draw.rectangle([btn_x, btn_y, btn_x + btn_w, btn_y + btn_h], fill=(32, 26, 22, 255), outline=C_BRASS_LIGHT, width=1)
    draw.text((btn_x + 14, btn_y + 7), "＋ シナリオを追加", font=f_body, fill=C_BRASS_LIGHT)

    # ウィンドウ操作ボタン（最小化・最大化・閉じる）
    draw.text((W - 110, 20), "―   □   ✕", font=f_small, fill=C_TEXT_MUTED)

    # ヘッダー下の装飾ディバイダー（真鍮ライン＋中央ダイヤ）
    line_y = 66
    draw.line([(24, line_y), (W - 24, line_y)], fill=C_BRASS_DARK, width=1)
    # 中央ダイヤ飾り
    mid_x = W // 2
    draw.polygon([(mid_x, line_y - 4), (mid_x + 4, line_y), (mid_x, line_y + 4), (mid_x - 4, line_y)], fill=C_BRASS_LIGHT)

    # =========================================================================
    # 4. 左側サイドバー（目録・分類棚） (x: 20〜270, y: 76〜770)
    # =========================================================================
    sb_left, sb_top, sb_right, sb_bottom = 24, 76, 270, 770
    # サイドバー背景
    draw.rectangle([sb_left, sb_top, sb_right, sb_bottom], fill=(22, 18, 15, 180), outline=C_BRASS_DARK, width=1)

    # 4.1 「⚜ システム分類」セクション
    draw.text((sb_left + 14, sb_top + 16), "⚜ システム分類", font=f_head, fill=C_BRASS_LIGHT)
    # 水平飾り線
    draw.line([(sb_left + 14, sb_top + 40), (sb_right - 14, sb_top + 40)], fill=C_BRASS_DARK, width=1)
    draw.polygon([(sb_left + 140, sb_top + 40 - 3), (sb_left + 143, sb_top + 40), (sb_left + 140, sb_top + 40 + 3), (sb_left + 137, sb_top + 40)], fill=C_BRASS_BASE)

    systems = [
        ("すべて", "18", False),
        ("クトゥルフ神話TRPG", "9", True),  # 選択中
        ("マーダーミステリー", "5", False),
        ("エモクロアTRPG", "2", False),
        ("その他", "2", False),
    ]
    cur_y = sb_top + 52
    for sys_name, count, selected in systems:
        if selected:
            # 選択中のハイライト（金枠＋微光）
            draw.rectangle([sb_left + 10, cur_y - 2, sb_right - 10, cur_y + 24], fill=(42, 33, 24, 255), outline=C_BRASS_LIGHT, width=1)
            draw.text((sb_left + 22, cur_y + 2), f"▶ {sys_name}", font=f_body, fill=C_BRASS_LIGHT)
            draw.text((sb_right - 36, cur_y + 2), count, font=f_small, fill=C_BRASS_LIGHT)
        else:
            draw.text((sb_left + 22, cur_y + 2), sys_name, font=f_body, fill=C_TEXT_WHITE)
            draw.text((sb_right - 36, cur_y + 2), count, font=f_small, fill=C_TEXT_MUTED)
        cur_y += 30

    # 4.2 「🏷 しおり・タグ」セクション
    cur_y += 14
    draw.text((sb_left + 14, cur_y), "🏷 しおり・タグ", font=f_head, fill=C_BRASS_LIGHT)
    cur_y += 24
    draw.line([(sb_left + 14, cur_y), (sb_right - 14, cur_y)], fill=C_BRASS_DARK, width=1)
    draw.polygon([(sb_left + 140, cur_y - 3), (sb_left + 143, cur_y), (sb_left + 140, cur_y + 3), (sb_left + 137, cur_y)], fill=C_BRASS_BASE)
    cur_y += 14

    # ピルタグの描画（詳細画面と同じ）
    tags = [
        ("CoC", (27, 94, 32)),
        ("マダミス", (106, 27, 154)),
        ("GM可", (160, 120, 28)),
        ("未通過", (21, 101, 192)),
        ("通過済み", (158, 42, 43)),
        ("6PL", (74, 60, 32)),
    ]
    tag_x, tag_y = sb_left + 14, cur_y
    for tname, tcolor in tags:
        tw = len(tname) * 16 + 24
        if tag_x + tw > sb_right - 14:
            tag_x = sb_left + 14
            tag_y += 32
        # ピル背景と枠
        draw.rounded_rectangle([tag_x, tag_y, tag_x + tw, tag_y + 24], radius=12, fill=(28, 23, 20, 255), outline=C_BRASS_BASE, width=1)
        # カラーインジケータ小さな丸
        draw.ellipse([tag_x + 8, tag_y + 8, tag_x + 16, tag_y + 16], fill=tcolor)
        draw.text((tag_x + 22, tag_y + 4), tname, font=f_small, fill=C_TEXT_WHITE)
        tag_x += tw + 8

    # 4.3 左下の羽ペン・懐中時計のアンティーク透かし画
    wm_resized = watermark_crop.resize((240, 150), Image.Resampling.LANCZOS)
    canvas.paste(wm_resized, (sb_left + 3, sb_bottom - 155), wm_resized if wm_resized.mode == 'RGBA' else None)

    # =========================================================================
    # 5. 右側メイン書架エリア（x: 285〜1255, y: 76〜770）
    # =========================================================================
    mb_left, mb_top, mb_right, mb_bottom = 286, 76, 1256, 770

    # 巨大な真鍮装飾フレーム（詳細画面右側フレームと全く同じ構造）
    draw.rectangle([mb_left, mb_top, mb_right, mb_bottom], fill=(22, 18, 15, 200), outline=C_BRASS_BASE, width=1)
    draw.rectangle([mb_left + 3, mb_top + 3, mb_right - 3, mb_bottom - 3], outline=C_BRASS_DARK, width=1)

    # 四隅のコーナー金具
    canvas.paste(corner_nw, (mb_left - 1, mb_top - 1), corner_nw if corner_nw.mode == 'RGBA' else None)
    canvas.paste(corner_ne, (mb_right - 24, mb_top - 1), corner_ne if corner_ne.mode == 'RGBA' else None)
    canvas.paste(corner_sw, (mb_left - 1, mb_bottom - 24), corner_sw if corner_sw.mode == 'RGBA' else None)
    canvas.paste(corner_se, (mb_right - 24, mb_bottom - 24), corner_se if corner_se.mode == 'RGBA' else None)

    # 上部見出し: 「⚜ 書架一覧 - クトゥルフ神話TRPG (9 冊)」
    canvas.paste(fleur_crop, (mb_left + 20, mb_top + 16), fleur_crop if fleur_crop.mode == 'RGBA' else None)
    draw.text((mb_left + 50, mb_top + 16), "書架一覧  ―  クトゥルフ神話TRPG  (9 冊)", font=f_head, fill=C_BRASS_LIGHT)
    draw.line([(mb_left + 380, mb_top + 28), (mb_right - 30, mb_top + 28)], fill=C_BRASS_DARK, width=1)
    draw.polygon([(mb_right - 100, mb_top + 28 - 3), (mb_right - 97, mb_top + 28), (mb_right - 100, mb_top + 28 + 3), (mb_right - 103, mb_top + 28)], fill=C_BRASS_BASE)

    # =========================================================================
    # 6. 書架グリッド（シナリオカード一覧）
    # =========================================================================
    # カードサイズ: 幅 215, 高さ 315
    # 列数: 4列, 行数: 2行
    cols, rows = 4, 2
    grid_start_x = mb_left + 24
    grid_start_y = mb_top + 55
    col_w = 230
    row_h = 325

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
        cx = grid_start_x + c * col_w
        cy = grid_start_y + r * row_h
        cw, ch = 215, 305

        is_hover = sc["hover"]

        # カード外枠と影
        if is_hover:
            # ホバー演出: 金色に輝く真鍮枠（二重）＋強いドロップシャドウ
            draw.rectangle([cx - 3, cy - 3, cx + cw + 3, cy + ch + 3], fill=(35, 28, 22, 255), outline=C_BRASS_LIGHT, width=2)
            draw.rectangle([cx, cy, cx + cw, cy + ch], fill=(28, 22, 18, 255), outline=C_BRASS_LIGHT, width=1)
        else:
            draw.rectangle([cx, cy, cx + cw, cy + ch], fill=C_CARD_BG, outline=C_BRASS_BASE, width=1)
            draw.rectangle([cx + 2, cy + 2, cx + cw - 2, cy + ch - 2], outline=C_BRASS_DARK, width=1)

        # 表紙サムネイル領域 (幅 195, 高さ 190) - 詳細画面の表紙枠と同一！
        tx, ty, tw, th = cx + 10, cy + 10, 195, 190
        draw.rectangle([tx, ty, tx + tw, ty + th], fill=(16, 13, 11, 255), outline=C_BRASS_BASE if not is_hover else C_BRASS_LIGHT, width=1)

        if sc["img"] is not None:
            # 切り出した実際の画像を描画
            scaled_cover = sc["img"].resize((tw - 4, th - 4), Image.Resampling.LANCZOS)
            canvas.paste(scaled_cover, (tx + 2, ty + 2))
        else:
            # ダミーの洋書・グリモワール表紙風グラフィック
            draw.rectangle([tx + 4, ty + 4, tx + tw - 4, ty + th - 4], fill=(24, 20, 17, 255), outline=C_BRASS_DARK, width=1)
            # 中央の紋章オーナメント
            draw.ellipse([tx + tw//2 - 18, ty + th//2 - 18, tx + tw//2 + 18, ty + th//2 + 18], outline=C_BRASS_BASE, width=1)
            draw.text((tx + tw//2 - 6, ty + th//2 - 8), "⚜", font=f_small, fill=C_BRASS_LIGHT)
            draw.text((tx + 20, ty + th - 36), sc["title"][:12], font=f_small, fill=C_BRASS_LIGHT)

        # 右上に虫眼鏡またはしおりリボン
        if is_hover:
            # 虫眼鏡アイコン（詳細画面の表紙右上と同じ）
            draw.rounded_rectangle([tx + tw - 26, ty + 6, tx + tw - 6, ty + 26], radius=4, fill=(35, 28, 22, 230), outline=C_BRASS_LIGHT, width=1)
            draw.text((tx + tw - 22, ty + 8), "🔍", font=f_small, fill=C_BRASS_LIGHT)
        else:
            # しおりピル
            tag_color = (27, 94, 32) if sc["tag"] == "CoC" else (106, 27, 154) if sc["tag"] == "マダミス" else (158, 42, 43)
            draw.rounded_rectangle([tx + tw - 58, ty + 6, tx + tw - 6, ty + 24], radius=9, fill=(28, 23, 20, 240), outline=C_BRASS_DARK, width=1)
            draw.ellipse([tx + tw - 52, ty + 10, tx + tw - 44, ty + 18], fill=tag_color)
            draw.text((tx + tw - 40, ty + 7), sc["tag"], font=f_small, fill=C_TEXT_WHITE)

        # カード下部情報
        # 題名（金文字）
        title_y = cy + 210
        draw.text((cx + 12, title_y), sc["title"], font=f_card_title, fill=C_BRASS_LIGHT if is_hover else C_TEXT_WHITE)

        # システム名
        sys_y = title_y + 20
        draw.text((cx + 12, sys_y), sc["system"], font=f_small, fill=C_BRASS_LIGHT if is_hover else C_TEXT_MUTED)

        # PL人数 & 時間（極小セピア文字）
        meta_y = sys_y + 18
        meta_text = f"👥 {sc['pl']}   ⏱ {sc['time']}"
        draw.text((cx + 12, meta_y), meta_text, font=f_small, fill=C_TEXT_MUTED)

        # 極薄い真鍮アンダーライン
        draw.line([(cx + 12, cy + ch - 12), (cx + cw - 12, cy + ch - 12)], fill=C_BRASS_MUTED, width=1)

    # =========================================================================
    # 7. 下部ステータスバー (y: 778 〜 808)
    # =========================================================================
    draw.line([(24, 776), (W - 24, 776)], fill=C_BRASS_DARK, width=1)
    draw.text((32, 786), "全 18 冊収蔵  │  選択中: 共犯者 (マーダーミステリー)  │  Rust FFI Engine: 正常稼働中", font=f_small, fill=C_TEXT_MUTED)
    draw.text((W - 260, 786), "📖 クリックで本を開く (詳細・編集)", font=f_small, fill=C_BRASS_LIGHT)

    # 保存
    out_dir = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449"
    out_path = os.path.join(out_dir, "preview_main_antique_design.png")
    canvas.save(out_path, format="PNG")
    print(f"Main design proposal saved to: {out_path}")

    # プロジェクトルートにもコピー保存
    canvas.save(r"M:\Tool\Cover_extractor\preview_main_antique_design.png", format="PNG")

if __name__ == "__main__":
    create_preview()
