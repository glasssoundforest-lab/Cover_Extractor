import os
from PIL import Image

src_path = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449\.user_uploaded\media_1792146845459_ff44e010.jpg"
img = Image.open(src_path)

# 表紙画像エリアの切り出し (x: 48, y: 118, w: 275, h: 290 付近)
# 左下の装飾エリア (x: 40, y: 810 付近)
# コーナー金具の確認
print("Source image loaded successfully.")
