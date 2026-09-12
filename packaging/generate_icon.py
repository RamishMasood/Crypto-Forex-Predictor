from pathlib import Path
from struct import pack


def rgba_icon(size: int) -> bytes:
    pixels = bytearray()
    cx = cy = size / 2
    radius = (size * 0.46) ** 2
    for y in range(size):
        for x in range(size):
            dx, dy = x - cx, y - cy
            if dx * dx + dy * dy <= radius:
                t = y / max(size - 1, 1)
                r = int(15 + 40 * t)
                g = int(90 + 90 * t)
                b = int(160 + 70 * (1 - t))
                a = 255
            else:
                r = g = b = a = 0
            pixels.extend((b, g, r, a))
    return bytes(pixels)


def dib(size: int, pixels: bytes) -> bytes:
    header = pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, len(pixels), 0, 0, 0, 0)
    stride = size * 4
    flipped = b"".join(pixels[i:i + stride] for i in range((size - 1) * stride, -1, -stride))
    mask_row = ((size + 31) // 32) * 4
    and_mask = b"\x00" * (mask_row * size)
    return header + flipped + and_mask


def make_ico(path: Path) -> None:
    images = [(size, dib(size, rgba_icon(size))) for size in (16, 32, 48, 256)]
    offset = 6 + 16 * len(images)
    buf = bytearray(pack("<HHH", 0, 1, len(images)))
    for size, data in images:
        w = 0 if size == 256 else size
        buf += pack("<BBBBHHII", w, w, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    for _, data in images:
        buf += data
    path.write_bytes(buf)


if __name__ == "__main__":
    make_ico(Path(__file__).with_name("quant_terminal.ico"))
    print("icon ok")
