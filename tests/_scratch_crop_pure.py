from PIL import Image

img = Image.open("Designer.png")
# 文字のない純粋なアート部分（y: 750 〜 1010, x: 45 〜 560）
pure_art = img.crop((45, 755, 560, 1010))
pure_art.save("crop_pure_art.png")
print("Saved pure art crop:", pure_art.size)
