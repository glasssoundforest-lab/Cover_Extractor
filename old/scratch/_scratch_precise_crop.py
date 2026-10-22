import os
from PIL import Image

src_path = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449\.user_uploaded\media_1792146845459_ff44e010.jpg"
img = Image.open(src_path)

# 表紙画像そのもの（黒い枠の中の共犯者イラスト部分）
# x: 50, y: 120 付近から幅270, 高さ155付近
cover_only = img.crop((48, 119, 324, 280))
cover_only.save("crop_cover_only.png")

# 羽ペンアイコン（タイトルバー左上）
quill_icon = img.crop((20, 10, 42, 32))
quill_icon.save("crop_quill.png")

# フルール・ド・リス（基本情報左）
fleur_icon = img.crop((374, 58, 396, 78))
fleur_icon.save("crop_fleur.png")

# コーナーブラケット金具（右側フレームの左上）
corner_nw = img.crop((361, 41, 385, 65))
corner_nw.save("crop_corner_nw.png")

# 表紙枠右上の虫眼鏡ボタン
search_icon = img.crop((293, 126, 318, 151))
search_icon.save("crop_search.png")

print("Cropped successfully!")
