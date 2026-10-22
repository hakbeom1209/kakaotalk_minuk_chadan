"""Synthetic local OCR benchmark; does not capture or save any real chat."""
from statistics import median
from time import perf_counter
from PIL import Image, ImageDraw, ImageFont
from kakao_filter.config import Settings
from kakao_filter.detector import TesseractNames, analyze


def main():
    image = Image.new("RGB", (1917, 820), (183, 205, 223))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=16)
    for y, name in ((60, "Alice"), (200, "Bob"), (600, "Carol")):
        draw.rounded_rectangle((16, y, 55, y+39), radius=15, fill=(152, 194, 229))
        draw.text((68, y-3), name, font=font, fill="black")
    draw.rounded_rectangle((68, 81, 140, 110), radius=3, fill="white")
    draw.rectangle((68, 221, 277, 460), fill=(82, 65, 45))
    draw.rounded_rectangle((68, 468, 1834, 532), radius=3, fill="white")
    draw.rounded_rectangle((68, 621, 180, 649), radius=3, fill="white")
    ocr = TesseractNames(Settings(ocrLanguage="eng"))
    settings = Settings(enabled=True, hiddenUsers=["Bob"], ocrLanguage="eng")
    start = perf_counter()
    boxes, _ = analyze(image, settings, ocr)
    cold = perf_counter()-start
    if len(boxes) != 2:
        raise RuntimeError("Synthetic OCR target was not recognized; inspect the OCR installation.")
    elapsed = []
    before = ocr.cache_stats()["misses"]
    for offset in (10, 20, 30, 35):
        shifted = Image.new("RGB", image.size, (183, 205, 223))
        shifted.paste(image, (0, -offset))
        start = perf_counter()
        found, diagnostic = analyze(shifted, settings, ocr, cache_only=True)
        elapsed.append(perf_counter()-start)
        if len(found) != 2 or diagnostic["pending"]:
            raise RuntimeError("Cached scroll result is incomplete.")
    print(f"Initial OCR analysis: {cold*1000:.1f} ms")
    print(f"Cached scroll analysis median: {median(elapsed)*1000:.1f} ms")
    print(f"Additional OCR misses after scrolling: {ocr.cache_stats()['misses']-before}")
    print("Synthetic analysis only; capture, Tk/Win32 painting, and actual PC latency are excluded.")


if __name__ == "__main__":
    main()
