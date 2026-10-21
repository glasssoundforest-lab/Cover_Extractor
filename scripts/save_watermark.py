from PIL import Image

src_path = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449\.user_uploaded\media_1792146845459_ff44e010.jpg"
img = Image.open(src_path)
wm = img.crop((30, 490, 340, 670))
wm.save(r"M:\Tool\Cover_extractor\gui_qt\assets\watermark.png")
print("Saved watermark asset.")
