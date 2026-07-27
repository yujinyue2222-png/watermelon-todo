# 生成西瓜todo手机版图标 icon.png (512x512)
from PIL import Image, ImageDraw

S = 512
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# 圆角背景（粉色）
r = 96
d.rounded_rectangle([0, 0, S, S], radius=r, fill=(255, 90, 122, 255))

cx, cy = S // 2, S // 2 + 30
R = 180

# 西瓜：外层绿皮
d.pieslice([cx - R, cy - R, cx + R, cy + R], 180, 360, fill=(60, 175, 90, 255))
# 白边
wr = R - 22
d.pieslice([cx - wr, cy - wr, cx + wr, cy + wr], 180, 360, fill=(240, 255, 240, 255))
# 红瓤
rr = R - 44
d.pieslice([cx - rr, cy - rr, cx + rr, cy + rr], 180, 360, fill=(255, 90, 100, 255))

# 西瓜籽
seeds = [(-70, 55), (0, 70), (70, 55), (-35, 100), (35, 100)]
for dx, dy in seeds:
    x, y = cx + dx, cy + dy
    d.ellipse([x - 9, y - 14, x + 9, y + 14], fill=(40, 40, 40, 255))

img.save("watermelon-todo/v2/icon.png")
print("icon.png saved")