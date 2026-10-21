import os
import math
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance

src_img = Image.open("Designer.png")
# クリーンなアート部分 (x: 52〜520, y: 795〜985)
clean_art = src_img.crop((52, 795, 520, 985))

# キャンバス解像度 (1920 x 1080)
W, H = 1920, 1080
canvas = Image.new("RGBA", (W, H), (20, 16, 13, 255))

# clean_art を拡大 (幅 1400, 高さ 540 程度)
target_w = 1400
target_h = int(clean_art.height * (target_w / clean_art.width))
art_scaled = clean_art.resize((target_w, target_h), Image.Resampling.LANCZOS)

# 左下の懐中時計・羽ペン・カリグラフィが、ウィンドウ内で一番美しく見える高さに配置
# 底辺から少し上に浮かせることで、下部バーに隠れずサイドバーと書架の奥にしっかり広がる
paste_y = H - target_h - 40
canvas.paste(art_scaled, (0, paste_y))

# 右上へ向けて滑らかにブレンドするためのマスク
mask = Image.new("L", (W, H), 0)
mdraw = ImageDraw.Draw(mask)
for y in range(H):
    for x in range(W):
        dist = math.sqrt((x * 0.85)**2 + ((H - y) * 1.0)**2)
        val = int(max(0, min(255, 255 - (dist / 1600) * 255)))
        mdraw.point((x, y), val)

mask = mask.filter(ImageFilter.GaussianBlur(35))

# ベースとなる黒檀・アンティークウッド
wood_base = Image.new("RGBA", (W, H), (18, 14, 11, 255))
blended = Image.composite(canvas, wood_base, mask)

# ビネット（周辺減光）
vignette = Image.new("L", (W, H), 0)
vdraw = ImageDraw.Draw(vignette)
cx, cy = W // 2, H // 2
max_r = math.sqrt(cx**2 + cy**2)
for y in range(0, H, 8):
    for x in range(0, W, 8):
        dist = math.sqrt((x - cx)**2 + (y - cy)**2)
        val = int(min(255, (dist / max_r) * 100))
        vdraw.rectangle([x, y, x + 8, y + 8], fill=val)
vignette = vignette.filter(ImageFilter.GaussianBlur(40))

dark_tone = Image.new("RGBA", (W, H), (12, 9, 8, 255))
final_bg = Image.composite(dark_tone, blended, vignette)

# コントラストと明度調整（ディテールをはっきり出す）
enhancer = ImageEnhance.Brightness(final_bg)
final_bg = enhancer.enhance(1.08)

out_path = r"M:\Tool\Cover_extractor\gui_qt\assets\window_bg.png"
final_bg.save(out_path, format="PNG")
print("Successfully generated balanced window background:", out_path)
