"""Light-theme avatar groups and sender-only OCR; no captured content is persisted."""
from __future__ import annotations
from dataclasses import dataclass
from collections import OrderedDict
from hashlib import blake2b
from threading import Lock
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


def join_ocr_words(data: dict, indices: list[int]) -> str:
    """Rejoin tightly spaced Hangul OCR tokens while retaining actual word gaps.

    Native Tesseract models split Korean names differently. Comparing token start
    against only the previous right edge used to invent spaces between syllables.
    This uses the measured gap; it never substitutes a different letter.
    """
    first = indices[0]
    text = data["text"][first]
    previous = first
    for index in indices[1:]:
        word = data["text"][index]
        gap = data["left"][index] - (data["left"][previous] + data["width"][previous])
        hangul = all("가" <= char <= "힣" for char in data["text"][previous] + word)
        limit = .20 * min(data["height"][previous], data["height"][index]) if hangul else 0
        text += ("" if gap <= limit else " ") + word
        previous = index
    return text


def bubble_candidates(image: Image.Image) -> list[Rect]:
    rgb = np.asarray(image.convert("RGB"))
    h, w = rgb.shape[:2]
    # White incoming bubbles only. Yellow outgoing bubbles and dark themes are excluded.
    red, green, blue = cv2.split(rgb)
    minimum = cv2.min(cv2.min(red, green), blue)
    maximum = cv2.max(cv2.max(red, green), blue)
    white = cv2.bitwise_and(cv2.compare(minimum, 235, cv2.CMP_GE),
                            cv2.compare(cv2.subtract(maximum, minimum), 15, cv2.CMP_LE))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(white, connectivity=8)
    boxes = []
    for index in range(1, count):
        x, y, bw, bh, area = map(int, stats[index])
        if (20 <= bw <= w - 30 and 18 <= bh <= h * .75
                and 25 <= x <= min(180, w * .40) and x + bw <= w - 6
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
        self._cache = OrderedDict()
        self._cache_lock = Lock()
        self._hits = 0
        self._misses = 0
        self._revision = 0
        if settings.tesseractPath:
            pytesseract.pytesseract.tesseract_cmd = settings.tesseractPath
        self.language = settings.ocrLanguage
        available = set(pytesseract.get_languages(config=""))
        missing = set(self.language.split("+")) - available
        if missing:
            raise RuntimeError("Tesseract 언어 데이터가 없습니다: " + ", ".join(sorted(missing)))

    def __call__(self, image: Image.Image, box: Rect, *, cache_only=False) -> list[Name] | None:
        # Only the narrow sender strip above each candidate, never the bubble body.
        left, top = max(0, box.x - 5), max(0, box.y - 35)
        right = min(image.width, box.x + 260)
        strip = image.crop((left, top, right, box.y))
        pixels = np.asarray(strip.convert("RGB"))
        white = (pixels.min(axis=2) >= 235) & (np.ptp(pixels, axis=2) <= 15)
        if white.mean() > .15:
            return []  # A preceding bubble overlaps the strip: sender attribution is unsafe.
        return self.read_strip(strip, left, top, cache_only=cache_only)

    def for_avatar(self, image: Image.Image, avatar: Rect, *, cache_only=False) -> list[Name] | None:
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
        return self.read_strip(strip.crop((x0, y0, x1, y1)), left+x0, top+y0, cache_only=cache_only)

    def cached_for_avatar(self, image: Image.Image, avatar: Rect) -> list[Name] | None:
        return self.for_avatar(image, avatar, cache_only=True)

    def cached_for_bubble(self, image: Image.Image, box: Rect) -> list[Name] | None:
        return self(image, box, cache_only=True)

    def cache_revision(self):
        with self._cache_lock:
            return self._revision

    def cache_stats(self):
        with self._cache_lock:
            return {"hits": self._hits, "misses": self._misses, "entries": len(self._cache)}

    @staticmethod
    def _translate(names, left, top):
        return [Name(n.text, Rect(n.bounds.x+left, n.bounds.y+top, n.bounds.width, n.bounds.height), n.confidence) for n in names]

    def read_strip(self, strip: Image.Image, left: int, top: int, *, cache_only=False) -> list[Name] | None:
        # Cache only identical nickname pixels, never avatar identity or screen y.
        # Coordinates are relative so a cached name follows a fresh detected tile.
        cache_key = (strip.size, self.language, blake2b(strip.tobytes(), digest_size=16).digest())
        with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached is not None:
                self._cache.move_to_end(cache_key)
                self._hits += 1
                return self._translate(cached, left, top)
            if not cache_only:
                self._misses += 1
        if cache_only:
            return None
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
            text = join_ocr_words(data, indices)
            result.append(Name(text,
                               Rect(left+x//3, top+y//3, (r-x+2)//3, (b-y+2)//3),
                               min(float(data["conf"][i]) for i in indices)))
        if len(result) == 1 and result[0].confidence >= 80:
            relative = self._translate(result, -left, -top)
            with self._cache_lock:
                self._cache[cache_key] = relative
                self._revision += 1
                self._cache.move_to_end(cache_key)
                while len(self._cache) > 256:
                    self._cache.popitem(last=False)
        return result


class AnalysisCancelled(Exception):
    """The source frame changed while OCR was running."""


def detect(image: Image.Image, settings: Settings, ocr: Callable, diagnostics: dict | None = None, readings: list | None = None, *, cache_only=False, cancelled=None) -> list[Rect]:
    if not settings.enabled or not settings.hiddenUsers:
        return []
    hidden = {normalize(name) for name in settings.hiddenUsers}
    result = []
    # Prefer avatar-anchored groups: a photo need not have a white bubble and
    # consecutive messages do not repeat the sender name.
    if cancelled and cancelled():
        raise AnalysisCancelled()
    groups = group_candidates(image)
    covered = []
    if diagnostics is not None:
        diagnostics.update(groups=len(groups), matched=0, unreadable=0)
        if cache_only:
            diagnostics["pending"] = False
    for avatar, boxes in groups[:60]:
        if cancelled and cancelled():
            raise AnalysisCancelled()
        covered.extend(boxes)
        if not hasattr(ocr, "for_avatar"):
            continue
        reader = getattr(ocr, "cached_for_avatar", None) if cache_only else ocr.for_avatar
        names = reader(image, avatar) if reader is not None else None
        if names is None:
            if diagnostics is not None:
                diagnostics["pending"] = True
            continue
        if readings is not None:
            readings.append({"y": avatar.y, "names": names,
                             "matched": len(names) == 1 and names[0].confidence >= 80 and normalize(names[0].text) in hidden})
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
        if cancelled and cancelled():
            raise AnalysisCancelled()
        if any(intersects(box, owned) for owned in covered):
            continue
        reader = getattr(ocr, "cached_for_bubble", None) if cache_only else ocr
        names = reader(image, box) if reader is not None else None
        if names is None:
            if diagnostics is not None:
                diagnostics["pending"] = True
            continue
        result.extend(associate([box], names, settings))
    return result


def intersects(a: Rect, b: Rect) -> bool:
    return a.x < b.x+b.width and b.x < a.x+a.width and a.y < b.y+b.height and b.y < a.y+a.height


def is_white_bubble(image: Image.Image, box: Rect) -> bool:
    pixels = np.asarray(image.crop((box.x, box.y, box.x+box.width, box.y+box.height)).convert("RGB"))
    return float(((pixels.min(axis=2) >= 235) & (np.ptp(pixels, axis=2) <= 15)).mean()) >= .70



def foreground_mask(image: Image.Image) -> np.ndarray:
    """Estimate a flat chat background from the most common quantized colour."""
    rgb = np.asarray(image.convert("RGB"))
    # The left gutter precedes avatars and bubbles, even for nearly full-width text.
    sample = rgb[::4, 2:min(10, rgb.shape[1])].astype(np.int32)
    codes = (sample[:, :, 0] // 8) * 1024 + (sample[:, :, 1] // 8) * 32 + sample[:, :, 2] // 8
    dominant = int(np.bincount(codes.ravel(), minlength=32768).argmax())
    pixels = sample[codes == dominant]
    background = np.median(pixels, axis=0)
    lower = tuple(int(max(0, value-28)) for value in background)
    upper = tuple(int(min(255, value+28)) for value in background)
    return cv2.bitwise_not(cv2.inRange(rgb, lower, upper))


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
        right = width - 6  # A maximized incoming bubble can occupy almost the entire width.
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
            pixels = np.asarray(image.crop((bx, by, bx+bw, by+bh)).convert("RGB"))[::3, ::3]
            yellow = (pixels[:, :, 0] >= 220) & (pixels[:, :, 1] >= 180) & (pixels[:, :, 2] <= 120)
            if yellow.mean() > .55:
                continue  # Wide outgoing yellow bubbles must not inherit an incoming sender.
            boxes.append(Rect(max(0, bx-2), max(0, by-2), min(width-bx+2, bw+4), min(height-by+2, bh+4)))
        if boxes and not ambiguous:
            result.append((avatar, sorted(boxes, key=lambda b: b.y)))
    return result


def analyze(image: Image.Image, settings: Settings, ocr: Callable, include_names: bool = False, *, cache_only=False, cancelled=None) -> tuple[list[Rect], dict]:
    """Collect only counts by default; opt-in nickname readings remain in memory."""
    diagnostics = {"groups": 0, "matched": 0, "unreadable": 0}
    readings = [] if include_names else None
    boxes = detect(image, settings, ocr, diagnostics, readings, cache_only=cache_only, cancelled=cancelled)
    if readings is not None:
        diagnostics["readings"] = readings
    return boxes, diagnostics
