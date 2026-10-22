import sys
import os
from PIL import Image

img_path = r"C:\Users\you05\.gemini\antigravity\brain\ed2e8c7c-e165-446a-9682-d086a9dab449\.user_uploaded\media_1792146845459_ff44e010.jpg"
if os.path.exists(img_path):
    img = Image.open(img_path)
    print(f"Detail image size: {img.size}, mode: {img.mode}")
else:
    print("File not found:", img_path)
