from PIL import Image

img = Image.open("Designer.png")
# 文字のない純粋なアート部分（y: 800 〜 980, x: 50 〜 550）
pure_art = img.crop((52, 795, 545, 985))
pure_art.save("crop_pure_art_clean.png")
print("Saved clean art crop:", pure_art.size)
