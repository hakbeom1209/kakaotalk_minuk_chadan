"""Conservative light-theme detector. No message text is OCRed or persisted."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable
import cv2
import numpy as np
from PIL import Image
from .config import Settings, normalize


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class Name:
    text: str
    bounds: Rect
    confidence: float


def bubble_candidates(image: Image.Image) -> list[Rect]:
    rgb = np.asarray(image.convert("RGB"))
    h, w = rgb.shape[:2]
    # White incoming bubbles only. Yellow outgoing bubbles and dark themes are excluded.
    white = ((rgb.min(axis=2) >= 235) & (np.ptp(rgb, axis=2) <= 15)).astype("uint8") * 255
    count, labels, stats, _ = cv2.connectedComponentsWithStats(white, connectivity=8)
    boxes = []
    for index in range(1, count):
        x, y, bw, bh, area = map(int, stats[index])
        if (20 <= bw <= w * .70 and 18 <= bh <= h * .75
                and 25 <= x <= w * .40 and x + bw < w * .88
                and y > 2 and y + bh < h - 2 and area / (bw * bh) >= .55):
            boxes.append(Rect(max(0, x - 2), max(0, y - 2), min(w - x + 2, bw + 4), min(h - y + 2, bh + 4)))
    return sorted(boxes, key=lambda b: (b.y, b.x))


def associate(boxes: list[Rect], names: list[Name], settings: Settings) -> list[Rect]:
    hidden = {normalize(n) for n in settings.hiddenUsers}
    matched = []
    for box in boxes:
        possible = [n for n in names if n.confidence >= 80
                    and 0 <= box.y - (n.bounds.y + n.bounds.height) <= 24
                    and abs(n.bounds.x - box.x) <= 24]
        # No fuzzy matches and no guessed inheritance across unnamed messages.
        if len(possible) == 1 and normalize(possible[0].text) in hidden:
            matched.append(box)
    return matched


class TesseractNames:
    def __init__(self, settings: Settings):
        import pytesseract
        self.engine = pytesseract
        if settings.tesseractPath:
            pytesseract.pytesseract.tesseract_cmd = settings.tesseractPath
        self.language = settings.ocrLanguage
        available = set(pytesseract.get_languages(config=""))
        missing = set(self.language.split("+")) - available
        if missing:
            raise RuntimeError("Tesseract 언어 데이터가 없습니다: " + ", ".join(sorted(missing)))

    def __call__(self, image: Image.Image, box: Rect) -> list[Name]:
        # Only the narrow sender strip above each candidate, never the bubble body.
        left, top = max(0, box.x - 5), max(0, box.y - 35)
        right = min(image.width, box.x + 260)
        strip = image.crop((left, top, right, box.y))
        pixels = np.asarray(strip.convert("RGB"))
        white = (pixels.min(axis=2) >= 235) & (np.ptp(pixels, axis=2) <= 15)
        if white.mean() > .15:
            return []  # A preceding bubble overlaps the strip: sender attribution is unsafe.
        strip = strip.resize(((right-left)*3, (box.y-top)*3))
        data = self.engine.image_to_data(strip, lang=self.language, config="--psm 7",
                                         output_type=self.engine.Output.DICT, timeout=3)
        lines: dict[tuple, list[int]] = {}
        for i, value in enumerate(data["text"]):
            if value.strip() and float(data["conf"][i]) >= 0:
                key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
                lines.setdefault(key, []).append(i)
        result = []
        for indices in lines.values():
            x = min(data["left"][i] for i in indices)
            y = min(data["top"][i] for i in indices)
            r = max(data["left"][i]+data["width"][i] for i in indices)
            b = max(data["top"][i]+data["height"][i] for i in indices)
            text = data["text"][indices[0]]
            previous_right = data["left"][indices[0]] + data["width"][indices[0]]
            for i in indices[1:]:
                # Tesseract sometimes splits adjacent Hangul syllables into overlapping words.
                separator = "" if data["left"][i] <= previous_right else " "
                text += separator + data["text"][i]
                previous_right = data["left"][i] + data["width"][i]
            result.append(Name(text,
                               Rect(left+x//3, top+y//3, (r-x+2)//3, (b-y+2)//3),
                               min(float(data["conf"][i]) for i in indices)))
        return result


def detect(image: Image.Image, settings: Settings, ocr: Callable) -> list[Rect]:
    if not settings.enabled or not settings.hiddenUsers:
        return []
    boxes = bubble_candidates(image)
    result = []
    for box in boxes[:60]:  # Bound OCR workload; unknown regions stay visible.
        # Conservative mode only supports text-like white bubbles. Photos/stickers are
        # intentionally not inferred from names; hideImages is a preference, not a guarantee.
        result.extend(associate([box], ocr(image, box), settings))
    return result
