"""Генерация resources/app.ico — щит с галочкой на индиго-градиенте."""

import os

from PIL import Image, ImageDraw


def build() -> str:
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Скруглённый квадрат-фон
    d.rounded_rectangle(
        [12, 12, size - 12, size - 12], radius=56, fill=(99, 102, 241, 255)
    )

    # Щит (полигон с скруглением низа через эллипс)
    shield = [(128, 52), (196, 78), (196, 138)]
    d.polygon(
        shield[:2] + [(196, 150), (128, 208), (60, 150), (60, 78)],
        fill=(255, 255, 255, 255),
    )

    # Галочка
    d.line(
        [(92, 130), (118, 158), (168, 100)],
        fill=(79, 70, 229, 255),
        width=18,
        joint="curve",
    )

    out_dir = os.path.join("resources")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "app.ico")
    img.save(
        out,
        sizes=[
            (16, 16),
            (24, 24),
            (32, 32),
            (48, 48),
            (64, 64),
            (128, 128),
            (256, 256),
        ],
    )
    return out


if __name__ == "__main__":
    print("icon:", build())
