"""本を開いた画面（詳細画面）とメイン画面（書架画面）の並列比較画像を生成
"""

from PIL import Image, ImageDraw, ImageFont

def render_comparison():
    src_detail = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449\.user_uploaded\media_1792146845459_ff44e010.jpg"
    src_main = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449\preview_main_grimoire_matched.png"

    img_detail = Image.open(src_detail).convert("RGBA")
    img_main = Image.open(src_main).convert("RGBA")

    # リサイズして並べる (高さ 650 に統一)
    target_h = 650
    # main 画面
    mw = int(img_main.width * (target_h / img_main.height))
    res_main = img_main.resize((mw, target_h), Image.Resampling.LANCZOS)

    # detail 画面
    dw = int(img_detail.width * (target_h / img_detail.height))
    res_detail = img_detail.resize((dw, target_h), Image.Resampling.LANCZOS)

    # 全体キャンバス (余白や見出しを入れる)
    pad = 20
    header_h = 70
    W = res_main.width + res_detail.width + pad * 3
    H = target_h + header_h + pad * 2

    canvas = Image.new("RGBA", (W, H), (15, 12, 10, 255))
    draw = ImageDraw.Draw(canvas)

    # フォント
    try:
        f_title = ImageFont.truetype("C:/Windows/Fonts/yumin.ttf", 22)
        f_sub = ImageFont.truetype("C:/Windows/Fonts/meiryo.ttc", 13)
        f_label = ImageFont.truetype("C:/Windows/Fonts/yumin.ttf", 16)
    except Exception:
        f_title = f_sub = f_label = ImageFont.load_default()

    # タイトル
    draw.text((pad, pad), "西洋古書・グリモワール調 世界観統一デザイン提案", font=f_title, fill=(212, 178, 111, 255))
    draw.text((pad, pad + 32), "左: 本を開く前の書架ライブラリ（メイン画面）  │  右: 本を開いた画面（あらすじ・詳細編集ダイアログ）", font=f_sub, fill=(160, 145, 128, 255))

    # 画像配置
    x_main = pad
    y_pos = pad + header_h
    canvas.paste(res_main, (x_main, y_pos))

    x_detail = x_main + res_main.width + pad
    canvas.paste(res_detail, (x_detail, y_pos))

    # 各画像のラベル枠
    draw.rectangle([x_main, y_pos - 26, x_main + 260, y_pos - 4], fill=(28, 22, 18, 255), outline=(140, 112, 62, 255))
    draw.text((x_main + 10, y_pos - 24), "【新装飾】魔導書架（メイン画面）", font=f_label, fill=(212, 178, 111, 255))

    draw.rectangle([x_detail, y_pos - 26, x_detail + 290, y_pos - 4], fill=(28, 22, 18, 255), outline=(140, 112, 62, 255))
    draw.text((x_detail + 10, y_pos - 24), "【本を開いた画面】詳細・あらすじ編集", font=f_label, fill=(212, 178, 111, 255))

    out_path = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449\preview_grimoire_comparison.png"
    canvas.save(out_path, format="PNG")
    print("Comparison saved to:", out_path)

if __name__ == "__main__":
    render_comparison()
