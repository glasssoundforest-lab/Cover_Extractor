import os
import math
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance

# Designer.png から左下の羽ペン・懐中時計・カリグラフィエリアを抽出
img = Image.open("Designer.png")
W_src, H_src = img.size

# 左下の机・羽ペン・懐中時計エリア
# x: 45〜580, y: 720〜1010
desk_art = img.crop((40, 720, 580, 1010))
desk_art.save("extracted_desk_art.png")
print("Extracted desk art size:", desk_art.size)

# 全画面背景の作成 (1920 x 1080)
BG_W, BG_H = 1920, 1080
bg = Image.new("RGBA", (BG_W, BG_H), (18, 14, 11, 255))

# 左下から中央にかけて羽ペン・懐中時計が美しく広がるように配置
# desk_art を拡大 (約 1200 x 640)
art_scaled = desk_art.resize((int(desk_art.width * 2.2), int(desk_art.height * 2.2)), Image.Resampling.LANCZOS)
aw, ah = art_scaled.size

# 左下に配置
bg.paste(art_scaled, (0, BG_H - ah))

# なめらかにダーク背景とブレンドするためのグラデーションマスク
mask = Image.new("L", (BG_W, BG_H), 0)
mdraw = ImageDraw.Draw(mask)
for y in range(BG_H):
    for x in range(BG_W):
        # 左下からの距離
        dist = math.sqrt(x**2 + (BG_H - y)**2)
        # 左下は明るく、右上に向かって徐々に暗いマホガニーウッドへフェード
        alpha = int(max(0, min(255, 255 - (dist / 1400) * 255)))
        mdraw.point((x, y), alpha)

mask = mask.filter(ImageFilter.GaussianBlur(30))

# 暗いアンティークマホガニーのベース
base_wood = Image.new("RGBA", (BG_W, BG_H), (16, 12, 10, 255))
final_bg = Image.composite(bg, base_wood, mask)

# ビネット（周辺減光）を追加
vignette = Image.new("L", (BG_W, BG_H), 0)
vdraw = ImageDraw.Draw(vignette)
cx, cy = BG_W // 2, BG_H // 2
max_r = math.sqrt(cx**2 + cy**2)
for y in range(0, BG_H, 8):
    for x in range(0, BG_W, 8):
        dist = math.sqrt((x - cx)**2 + (y - cy)**2)
        val = int(min(255, (dist / max_r) * 140))
        vdraw.rectangle([x, y, x + 8, y + 8], fill=val)
vignette = vignette.filter(ImageFilter.GaussianBlur(40))

dark_overlay = Image.new("RGBA", (BG_W, BG_H), (10, 8, 7, 255))
final_bg = Image.composite(dark_overlay, final_bg, vignette)

# 文字が読みやすくなるよう、わずかにコントラストと暗さを調整
enhancer = ImageEnhance.Brightness(final_bg)
final_bg = enhancer.enhance(0.95)

# 保存
out_path = r"M:\Tool\Cover_extractor\gui_qt\assets\window_bg.png"
final_bg.save(out_path, format="PNG")
print("Saved window background to:", out_path)
