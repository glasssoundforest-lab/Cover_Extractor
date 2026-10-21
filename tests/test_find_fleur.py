from PIL import Image

src_path = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449\.user_uploaded\media_1792146845459_ff44e010.jpg"
img = Image.open(src_path)

# 基本情報周辺 (x: 360〜450, y: 70〜120 付近)
info_header = img.crop((365, 75, 450, 115))
info_header.save("crop_info_header.png")
