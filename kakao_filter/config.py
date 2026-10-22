from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
import tempfile
import unicodedata


def normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).split())


@dataclass
class Settings:
    enabled: bool = False
    hiddenUsers: list[str] = field(default_factory=list)
    displayMode: str = "opaque"
    chatScope: str = "selected"
    selectedChats: list[str] = field(default_factory=list)
    hideImages: bool = True
    autoStart: bool = False
    topMargin: int = 75
    bottomMargin: int = 110
    intervalMs: int = 800
    ocrLanguage: str = "kor+eng"
    tesseractPath: str = ""

    @classmethod
    def parse(cls, raw: dict) -> Settings:
        if not isinstance(raw, dict):
            raise ValueError("설정은 JSON 객체여야 합니다.")
        s = cls(**{k: v for k, v in raw.items() if k in cls.__dataclass_fields__})
        for key in ("enabled", "hideImages", "autoStart"):
            if type(getattr(s, key)) is not bool:
                raise ValueError(f"{key}: 참/거짓 값이 필요합니다.")
        for key in ("hiddenUsers", "selectedChats"):
            values = getattr(s, key)
            if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
                raise ValueError(f"{key}: 문자열 목록이 필요합니다.")
            setattr(s, key, list(dict.fromkeys(normalize(v) for v in values if normalize(v))))
        if s.displayMode not in {"opaque", "placeholder", "blur"}:
            raise ValueError("지원하지 않는 표시 방식입니다.")
        if s.chatScope not in {"all", "selected"}:
            raise ValueError("지원하지 않는 채팅방 범위입니다.")
        for key, low, high in (("topMargin", 0, 500), ("bottomMargin", 0, 500), ("intervalMs", 300, 5000)):
            value = getattr(s, key)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{key}: {low}~{high} 사이의 정수가 필요합니다.")
        if not isinstance(s.ocrLanguage, str) or s.ocrLanguage not in {"kor", "eng", "kor+eng"}:
            raise ValueError("OCR 언어는 kor, eng, kor+eng 중 하나여야 합니다.")
        if not isinstance(s.tesseractPath, str):
            raise ValueError("Tesseract 경로는 문자열이어야 합니다.")
        return s

    def applies(self, title: str) -> bool:
        return self.enabled and bool(self.hiddenUsers) and (
            self.chatScope == "all" or normalize(title) in self.selectedChats
        )


def config_path() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".config"))) / "KakaoMessageFilter" / "settings.json"


def load(path: Path) -> Settings:
    if not path.exists():
        return Settings()
    return Settings.parse(json.loads(path.read_text(encoding="utf-8")))


def save(path: Path, settings: Settings) -> None:
    checked = Settings.parse(asdict(settings))
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".settings-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(asdict(checked), out, ensure_ascii=False, indent=2)
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)
