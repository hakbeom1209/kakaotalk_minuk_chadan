"""Latest-frame scheduling: cached names can mask while old OCR is still finishing."""
from concurrent.futures import CancelledError
from threading import Event
from .detector import AnalysisCancelled, analyze


class LatestFrameAnalyzer:
    def __init__(self, executor, analyze_frame=analyze):
        self.executor = executor
        self.analyze_frame = analyze_frame
        self.future = None
        self.stop = Event()
        self.latest_key = None
        self.submitted_key = None
        self.ready = None
        self.preview = None
        self.preview_key = None

    @property
    def has_work(self):
        return self.future is not None

    def cancel(self):
        self.stop.set()
        if self.future is not None:
            self.future.cancel()
        self.latest_key = None
        self.ready = None
        self.preview = None
        self.preview_key = None

    def request(self, image, settings, ocr, key, include_names=False):
        if key != self.latest_key:
            self.stop.set()  # The running subprocess may finish, but no more old names are read.
            self.latest_key = key
            self.ready = None
            self.preview_key = None
        if self.future is not None and self.future.done():
            future, submitted = self.future, self.submitted_key
            self.future = None
            try:
                result = future.result()
            except (AnalysisCancelled, CancelledError):
                result = None
            except Exception:
                if submitted == key:
                    raise
                result = None  # An obsolete frame cannot fail a newer valid cached preview.
            if result is not None and submitted == key:
                self.ready = (key, result)
        if self.ready is not None and self.ready[0] == key:
            return self.ready[1]
        revision = ocr.cache_revision() if hasattr(ocr, "cache_revision") else 0
        preview_key = (key, revision, include_names)
        if preview_key != self.preview_key:
            self.preview = self.analyze_frame(image, settings, ocr, include_names, cache_only=True)
            self.preview_key = preview_key
        if self.preview[1].get("pending") and self.future is None:
            self.stop = Event()
            self.submitted_key = key
            self.future = self.executor.submit(self.analyze_frame, image, settings, ocr, include_names,
                                               cancelled=self.stop.is_set)
        return self.preview
