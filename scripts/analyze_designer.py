from PIL import Image

img = Image.open("Designer.png")
print("Designer.png size:", img.size)

# 左下エリアの切り出し (x: 0〜600, y: 700〜1280 付近)
w, h = img.size
left_bottom = img.crop((0, int(h * 0.55), int(w * 0.45), h))
left_bottom.save("crop_designer_lb.png")
print("Saved left_bottom crop:", left_bottom.size)
