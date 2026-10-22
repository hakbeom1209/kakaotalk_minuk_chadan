from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import shutil
import sys
import time

from .config import Settings, config_path, load, save


def doctor(language, executable):
    import pytesseract
    if executable:
        pytesseract.pytesseract.tesseract_cmd = executable
    elif sys.platform == "win32" and not shutil.which("tesseract"):
        from pathlib import Path
        candidate = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
        if candidate.exists():
            pytesseract.pytesseract.tesseract_cmd = str(candidate)
    print("Python:", sys.version.split()[0])
    print("실시간 Windows 지원:", sys.platform == "win32")
    print("Tesseract:", pytesseract.get_tesseract_version())
    available = pytesseract.get_languages(config="")
    print("OCR 언어:", ", ".join(available))
    if set(language.split("+")) - set(available):
        raise RuntimeError("필요한 OCR 언어 데이터가 없습니다: " + language)
    return pytesseract.pytesseract.tesseract_cmd


class Application:
    def __init__(self, root, path):
        import tkinter as tk
        from tkinter import ttk, messagebox
        from . import windows
        from .overlay import Overlay
        self.tk, self.ttk, self.messagebox = tk, ttk, messagebox
        self.win, self.root, self.path = windows, root, path
        self.overlay = Overlay(root)
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.future = None
        self.generation = 0
        self.active = False
        self.closed = False
        self.last_target = None
        self.next_capture = 0
        self.displayed_frame = None
        self.ocr = None
        try:
            self.settings = load(path)
        except (ValueError, OSError) as exc:
            messagebox.showerror("설정 오류", f"기존 설정은 보존합니다.\n{exc}")
            self.settings = Settings()
        root.title("Kakao Message Filter · 실험 버전")
        root.geometry("680x760")
        root.minsize(620, 700)
        root.protocol("WM_DELETE_WINDOW", self.close)
        frame = ttk.Frame(root, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="카카오톡 메시지 가리기", font=("맑은 고딕", 19, "bold")).pack(anchor="w")
        ttk.Label(frame, text="이 PC 화면에서만 처리 · 메시지 저장/전송 없음").pack(anchor="w", pady=(4, 12))
        self.status = tk.StringVar(value="중지됨 · 대상 채팅창을 선택하세요")
        ttk.Label(frame, textvariable=self.status, wraplength=620).pack(anchor="w", pady=6)
        self.enabled = tk.BooleanVar(value=self.settings.enabled)
        ttk.Checkbutton(frame, text="필터 켜기 (설정 저장 후 적용)", variable=self.enabled, command=self.disable_now).pack(anchor="w")
        ttk.Label(frame, text="숨길 닉네임 (한 줄에 한 명, 띄어쓰기 포함 정확히 입력)").pack(anchor="w", pady=(12, 4))
        self.names = tk.Text(frame, height=4)
        self.names.pack(fill="x")
        self.names.insert("1.0", "\n".join(self.settings.hiddenUsers))
        ttk.Label(frame, text="같은 닉네임의 참여자는 구별할 수 없습니다. 동명이인이 없는 방에서 사용하세요.", wraplength=620).pack(anchor="w", pady=4)
        bar = ttk.Frame(frame)
        bar.pack(fill="x", pady=8)
        ttk.Button(bar, text="카카오톡 창 새로 찾기", command=self.refresh).pack(side="left")
        self.combo = ttk.Combobox(bar, state="readonly", width=40)
        self.combo.pack(side="left", padx=8)
        self.combo.bind("<<ComboboxSelected>>", lambda _: self.invalidate())
        self.all_chats = tk.BooleanVar(value=self.settings.chatScope == "all")
        ttk.Checkbutton(frame, text="모든 카카오톡 창에 적용 (단체방 여부는 자동 판별하지 않음)", variable=self.all_chats, command=self.invalidate).pack(anchor="w")
        ttk.Label(frame, text="선택 채팅방 제목 (한 줄에 하나, 창 제목과 정확히 일치)").pack(anchor="w", pady=(8, 4))
        self.chats = tk.Text(frame, height=3)
        self.chats.pack(fill="x")
        self.chats.insert("1.0", "\n".join(self.settings.selectedChats))
        ttk.Button(frame, text="현재 선택 창 제목을 목록에 추가", command=self.add_chat).pack(anchor="w", pady=4)
        options = ttk.Frame(frame)
        options.pack(fill="x", pady=8)
        ttk.Label(options, text="표시 방식").grid(row=0, column=0, sticky="w")
        self.mode = ttk.Combobox(options, values=["opaque", "placeholder", "blur"], state="readonly", width=15)
        self.mode.set(self.settings.displayMode)
        self.mode.grid(row=0, column=1, padx=8)
        self.top = tk.StringVar(value=str(self.settings.topMargin))
        self.bottom = tk.StringVar(value=str(self.settings.bottomMargin))
        for row, label, variable in ((1, "상단 제외 높이(px)", self.top), (2, "하단 입력창 제외 높이(px)", self.bottom)):
            ttk.Label(options, text=label).grid(row=row, column=0, sticky="w", pady=3)
            ttk.Entry(options, textvariable=variable, width=10).grid(row=row, column=1)
        self.autostart = tk.BooleanVar(value=self.settings.autoStart)
        ttk.Checkbutton(frame, text="Windows 로그인 시 실행", variable=self.autostart).pack(anchor="w")
        ttk.Label(frame, text="지원: 밝은 테마의 흰색 수신 말풍선 + 바로 위 발신자 이름.\n연속 메시지·사진·이모티콘·답장·어두운 테마는 미지원입니다.\n인식 전 순간 노출이 있으며 완전한 차단 수단이 아닙니다.", wraplength=620).pack(anchor="w", pady=8)
        ttk.Button(frame, text="설정 저장 및 적용", command=self.apply).pack(fill="x", pady=6)
        ttk.Label(frame, text=f"설정: {path}", wraplength=620).pack(anchor="w")
        self.refresh()
        # Load enabled state only after OCR prerequisites have been validated.
        if self.settings.enabled:
            self.start()
        root.after(100, self.tick)

    def invalidate(self):
        self.generation += 1
        self.last_target = None
        self.displayed_frame = None
        self.next_capture = 0
        self.overlay.clear()

    def disable_now(self):
        if not self.enabled.get():
            self.active = False
            self.invalidate()
            self.status.set("중지됨")

    def refresh(self):
        self.invalidate()
        self.windows = self.win.list_windows()
        self.combo["values"] = [f"{w.title} [창 {w.hwnd}]" for w in self.windows]
        if self.windows:
            self.combo.current(0)
        else:
            self.combo.set("")

    def add_chat(self):
        index = self.combo.current()
        if index >= 0:
            title = self.windows[index].title
            current = self.chats.get("1.0", "end").splitlines()
            if title not in current:
                self.chats.insert("end", title + "\n")

    def apply(self):
        self.active = False
        self.invalidate()
        try:
            raw = asdict(self.settings)
            raw.update(enabled=self.enabled.get(), hiddenUsers=self.names.get("1.0", "end").splitlines(),
                       selectedChats=self.chats.get("1.0", "end").splitlines(),
                       chatScope="all" if self.all_chats.get() else "selected", displayMode=self.mode.get(),
                       topMargin=int(self.top.get()), bottomMargin=int(self.bottom.get()), autoStart=self.autostart.get())
            settings = Settings.parse(raw)
            if settings.enabled and (not settings.hiddenUsers or (settings.chatScope == "selected" and not settings.selectedChats)):
                raise ValueError("숨길 닉네임과 적용할 채팅방을 입력하세요.")
            self.win.set_autostart(settings.autoStart)
            save(self.path, settings)
            self.settings = settings
            if settings.enabled:
                self.start()
            else:
                self.status.set("저장됨 · 필터 중지")
        except Exception as exc:
            self.messagebox.showerror("설정 적용 실패", str(exc))
            self.status.set("중지됨 · 설정 또는 OCR 설치를 확인하세요")

    def start(self):
        try:
            from .detector import TesseractNames
            executable = doctor(self.settings.ocrLanguage, self.settings.tesseractPath)
            self.settings.tesseractPath = executable
            self.ocr = TesseractNames(self.settings)
            self.active = True
            self.status.set("대기 중 · 카카오톡 채팅창을 맨 앞으로 가져오세요")
        except Exception as exc:
            self.active = False
            self.messagebox.showerror("OCR 준비 실패", str(exc))

    def target(self):
        hwnd = self.win.foreground()
        current = self.win.inspect(hwnd) if hwnd else None
        if not current or not self.settings.applies(current.title):
            return None
        if not self.all_chats.get():
            index = self.combo.current()
            if index < 0 or current.hwnd != self.windows[index].hwnd:
                return None
        return current

    def capture(self, target):
        from PIL import Image
        import mss
        x, y, width, height = target.bounds
        top, bottom = self.settings.topMargin, self.settings.bottomMargin
        if width < 200 or height - top - bottom < 60:
            raise ValueError("채팅 영역이 너무 작습니다.")
        with mss.mss() as capture:
            shot = capture.grab({"left": x, "top": y+top, "width": width, "height": height-top-bottom})
            return Image.frombytes("RGB", shot.size, shot.rgb)

    @staticmethod
    def same_frame(first, second):
        return first.size == second.size and first.tobytes() == second.tobytes()

    def tick(self):
        if self.closed:
            return
        from PIL import Image
        from .detector import detect
        try:
            target = self.target() if self.active else None
            if not target or target != self.last_target:
                self.overlay.clear()
                self.displayed_frame = None
            if target and self.displayed_frame is not None:
                if not self.same_frame(self.capture(target), self.displayed_frame):
                    self.overlay.clear()
                    self.displayed_frame = None
                    self.next_capture = 0
            if self.future is not None:
                if self.future.done():
                    future, metadata = self.future, self.pending
                    self.future = None
                    boxes = future.result()
                    generation, previous, image, origin = metadata
                    if (self.active and target == previous and generation == self.generation
                            and self.same_frame(image, self.capture(target))):
                        self.overlay.show(image, boxes, origin, self.settings.displayMode)
                        self.status.set(f"실행 중 · 가림막 {len(boxes)}개 · 이름 미확인 메시지는 표시")
                        self.displayed_frame = image
                        self.next_capture = time.monotonic() + self.settings.intervalMs / 1000
                else:
                    self.root.after(60, self.tick)
                    return
            if target and self.active and time.monotonic() >= self.next_capture:
                x, y, width, height = target.bounds
                top, bottom = self.settings.topMargin, self.settings.bottomMargin
                if width < 200 or height - top - bottom < 60:
                    raise ValueError("채팅 영역이 너무 작습니다. 창 크기와 제외 높이를 확인하세요.")
                image = self.capture(target)
                # Remove stale masks while new content is being recognized.
                self.overlay.clear()
                self.pending = (self.generation, target, image, (x, y+top))
                self.future = self.executor.submit(detect, image, self.settings, self.ocr)
                self.last_target = target
            elif self.active and not target:
                self.status.set("대기 중 · 적용 대상 카카오톡 창이 전면에 없습니다")
        except Exception as exc:
            self.active = False
            self.overlay.clear()
            # Do not log OCR data or captured pixels.
            self.status.set("필터 중지 · OCR/캡처 오류. 설치와 권한을 확인하세요.")
            self.messagebox.showerror("필터 오류", type(exc).__name__ + ": 화면 인식에 실패했습니다. --doctor로 OCR 설치를 확인하세요.")
        self.root.after(60, self.tick)

    def close(self):
        self.closed = True
        self.active = False
        self.overlay.clear()
        if self.future:
            self.future.cancel()
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description="카카오톡 로컬 화면 가림막 (Windows 실험 버전)")
    parser.add_argument("--doctor", action="store_true", help="OCR 설치와 언어 데이터 확인")
    parser.add_argument("--language", default="kor+eng", choices=["kor", "eng", "kor+eng"])
    args = parser.parse_args()
    if args.doctor:
        try:
            doctor(args.language, "")
        except Exception as exc:
            parser.exit(1, f"OCR 준비 실패: {exc}\n")
        return
    if sys.platform != "win32":
        parser.exit(1, "실시간 화면 필터는 Windows 10(2004 이상)/11에서 실행하세요.\n")
    from . import windows
    windows.dpi_aware()
    import tkinter as tk
    root = tk.Tk()
    Application(root, config_path())
    root.mainloop()
