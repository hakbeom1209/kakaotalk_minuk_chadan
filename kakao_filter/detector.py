"""Light-theme avatar groups and sender-only OCR; no captured content is persisted."""
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
        return self.read_strip(strip, left, top)

    def for_avatar(self, image: Image.Image, avatar: Rect) -> list[Name]:
        scale = avatar.width / 40
        left = avatar.x + avatar.width + round(8 * scale)
        top = max(0, avatar.y - round(3 * scale))
        right = min(image.width, left + round(260 * scale))
        bottom = min(image.height, avatar.y + round(20 * scale))
        strip = image.crop((left, top, right, bottom))
        # The sender strip should contain only dark glyphs on a flat background.
        pixels = np.asarray(strip.convert("RGB"))
        ink = (pixels.max(axis=2) < 145).astype(np.uint8)
        ys, xs = np.where(ink)
        if len(xs) < 6:
            return []
        # Tight bounds improve small Korean name OCR without reading message bodies.
        x0, y0 = max(0, int(xs.min())-4), max(0, int(ys.min())-3)
        x1, y1 = min(strip.width, int(xs.max())+5), min(strip.height, int(ys.max())+4)
        return self.read_strip(strip.crop((x0, y0, x1, y1)), left+x0, top+y0)

    def read_strip(self, strip: Image.Image, left: int, top: int) -> list[Name]:
        strip = strip.resize((strip.width*3, strip.height*3))
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


def detect(image: Image.Image, settings: Settings, ocr: Callable, diagnostics: dict | None = None) -> list[Rect]:
    if not settings.enabled or not settings.hiddenUsers:
        return []
    hidden = {normalize(name) for name in settings.hiddenUsers}
    result = []
    # Prefer avatar-anchored groups: a photo need not have a white bubble and
    # consecutive messages do not repeat the sender name.
    groups = group_candidates(image)
    covered = []
    if diagnostics is not None:
        diagnostics.update(groups=len(groups), matched=0, unreadable=0)
    for avatar, boxes in groups[:60]:
        covered.extend(boxes)
        if not hasattr(ocr, "for_avatar"):
            continue
        names = ocr.for_avatar(image, avatar)
        if len(names) != 1 or names[0].confidence < 80:
            if diagnostics is not None:
                diagnostics["unreadable"] += 1
            continue
        if normalize(names[0].text) not in hidden:
            continue
        if diagnostics is not None:
            diagnostics["matched"] += 1
        for box in boxes:
            if settings.hideImages or is_white_bubble(image, box):
                result.append(box)
    # Legacy direct-name path is used only for candidates outside avatar groups.
    for box in bubble_candidates(image)[:60]:
        if any(intersects(box, owned) for owned in covered):
            continue
        result.extend(associate([box], ocr(image, box), settings))
    return result


def intersects(a: Rect, b: Rect) -> bool:
    return a.x < b.x+b.width and b.x < a.x+a.width and a.y < b.y+b.height and b.y < a.y+a.height


def is_white_bubble(image: Image.Image, box: Rect) -> bool:
    pixels = np.asarray(image.crop((box.x, box.y, box.x+box.width, box.y+box.height)).convert("RGB"))
    return float(((pixels.min(axis=2) >= 235) & (np.ptp(pixels, axis=2) <= 15)).mean()) >= .70



def foreground_mask(image: Image.Image) -> np.ndarray:
    """Estimate a flat chat background from the most common quantized colour."""
    rgb = np.asarray(image.convert("RGB"))
    sample = rgb[::4, ::4].astype(np.int32)
    codes = (sample[:, :, 0] // 8) * 1024 + (sample[:, :, 1] // 8) * 32 + sample[:, :, 2] // 8
    dominant = int(np.bincount(codes.ravel(), minlength=32768).argmax())
    pixels = sample[codes == dominant]
    background = np.median(pixels, axis=0)
    distance = np.max(np.abs(rgb.astype(np.int16) - background), axis=2)
    return (distance > 28).astype(np.uint8) * 255


def avatar_candidates(image: Image.Image, mask: np.ndarray) -> list[Rect]:
    """Profile tiles are group boundaries, even if the next name cannot be OCRed."""
    h, w = mask.shape
    # KakaoTalk's avatar lane stays near the left edge even when maximized.
    lane = min(110, w // 5)
    closed = cv2.morphologyEx(mask[:, :lane], cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    count, _, stats, _ = cv2.connectedComponentsWithStats(closed, connectivity=8)
    candidates = []
    for x, y, bw, bh, area in stats[1:]:
        x, y, bw, bh, area = map(int, (x, y, bw, bh, area))
        clipped = y <= 2 or y + bh >= h - 2
        if (20 <= bw <= 72 and 8 <= bh <= 72
                and (clipped or (bh >= 20 and .70 <= bw / bh <= 1.40))
                and 4 <= x <= 35 and x + bw <= lane - 2
                and area >= bw * bh * .35):
            candidates.append(Rect(x, y, bw, bh))
    return sorted(candidates, key=lambda b: b.y)


def group_candidates(image: Image.Image) -> list[tuple[Rect, list[Rect]]]:
    """Associate media/text components with a visible avatar, never across a new tile.

    Right-side outgoing messages and messages above the first avatar are not owned.
    If a component runs across a group boundary, the ambiguous group is rejected.
    """
    mask = foreground_mask(image)
    avatars = avatar_candidates(image, mask)
    height, width = mask.shape
    result = []
    for index, avatar in enumerate(avatars):
        if avatar.y <= 2 or avatar.y + avatar.height >= height - 2:
            continue  # Clipped avatars may bound other groups but cannot establish ownership.
        scale = avatar.width / 40
        left = avatar.x + avatar.width + round(12 * scale)
        top = avatar.y + round(21 * scale)
        bottom = avatars[index + 1].y - round(4 * scale) if index + 1 < len(avatars) else height
        right = min(width - 10, max(left + 40, round(width * .92)))
        if bottom <= top or right <= left:
            continue
        # Include a small margin for the bubble tail but exclude avatar/name columns.
        start = max(0, left - round(6 * scale))
        region = mask[top:bottom, start:right]
        closed = cv2.morphologyEx(region, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        count, _, stats, _ = cv2.connectedComponentsWithStats(closed, connectivity=8)
        boxes = []
        ambiguous = False
        for x, y, bw, bh, area in stats[1:]:
            x, y, bw, bh, area = map(int, (x, y, bw, bh, area))
            # Only left-aligned content belongs to this sender. Timestamps are ignored.
            if x > round(48 * scale) or bw < round(20 * scale) or bh < round(16 * scale):
                continue
            if area < 100 * scale * scale:
                continue
            # Don't truncate a large object that extends outside the incoming lane.
            if x + bw >= region.shape[1] - 1 or (index + 1 < len(avatars) and y + bh >= region.shape[0] - 1):
                ambiguous = True
                break
            bx, by = start + x, top + y
            boxes.append(Rect(max(0, bx-2), max(0, by-2), min(width-bx+2, bw+4), min(height-by+2, bh+4)))
        if boxes and not ambiguous:
            result.append((avatar, sorted(boxes, key=lambda b: b.y)))
    return result


def analyze(image: Image.Image, settings: Settings, ocr: Callable) -> tuple[list[Rect], dict]:
    """Return content-free counts so the UI can distinguish detection failures."""
    diagnostics = {"groups": 0, "matched": 0, "unreadable": 0}
    boxes = detect(image, settings, ocr, diagnostics)
    return boxes, diagnostics
