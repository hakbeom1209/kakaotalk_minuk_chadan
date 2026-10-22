from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from kakao_filter.pipeline import LatestFrameAnalyzer
from kakao_filter.detector import Rect, AnalysisCancelled


def test_cached_current_frame_does_not_wait_for_an_old_ocr_job():
    started, release = Event(), Event()
    calls = []
    def backend(image, settings, ocr, include_names=False, *, cache_only=False, cancelled=None):
        if cache_only:
            return ([Rect(10, 90, 40, 20)], {"pending": False}) if image == "new" else ([], {"pending": True})
        calls.append(image)
        started.set()
        assert release.wait(2)
        return [Rect(10, 10, 40, 20)], {}  # Deliberately return a stale result.
    with ThreadPoolExecutor(max_workers=1) as pool:
        pipeline = LatestFrameAnalyzer(pool, backend)
        pipeline.request("old", None, None, 1)
        assert started.wait(1)
        try:
            current = pipeline.request("new", None, None, 2)
            assert current[0] == [Rect(10, 90, 40, 20)]
            assert not pipeline.future.done()
            assert pipeline.stop.is_set()
        finally:
            release.set()
        pipeline.future.result(timeout=1)
        assert pipeline.request("new", None, None, 2)[0] == current[0]
        assert calls == ["old"]  # No extra subprocess needed for cached names.


def test_scroll_does_not_queue_every_intermediate_frame():
    started, release = Event(), Event()
    calls = []
    def backend(image, settings, ocr, include_names=False, *, cache_only=False, cancelled=None):
        if cache_only:
            return [], {"pending": True}
        calls.append(image)
        if image == "old":
            started.set()
            assert release.wait(2)
            if cancelled():
                raise AnalysisCancelled()
        return [image], {}
    with ThreadPoolExecutor(max_workers=1) as pool:
        pipeline = LatestFrameAnalyzer(pool, backend)
        pipeline.request("old", None, None, 1)
        assert started.wait(1)
        try:
            for serial in (2, 3, 4):
                pipeline.request(f"scroll-{serial}", None, None, serial)
            assert calls == ["old"]
        finally:
            release.set()
        try:
            pipeline.future.result(timeout=1)
        except AnalysisCancelled:
            pass
        pipeline.request("scroll-4", None, None, 4)
        pipeline.future.result(timeout=1)
        assert pipeline.request("scroll-4", None, None, 4)[0] == ["scroll-4"]
        assert calls == ["old", "scroll-4"]


def test_completed_names_can_be_used_while_other_names_are_still_running():
    started, release = Event(), Event()
    cache = SimpleNamespace(revision=0)
    cache.cache_revision = lambda: cache.revision
    def backend(image, settings, ocr, include_names=False, *, cache_only=False, cancelled=None):
        if cache_only:
            return (["known-mask"] if cache.revision else []), {"pending": True}
        started.set()
        assert release.wait(2)
        return ["known-mask", "new-mask"], {}
    with ThreadPoolExecutor(max_workers=1) as pool:
        pipeline = LatestFrameAnalyzer(pool, backend)
        assert pipeline.request("frame", None, cache, 1)[0] == []
        assert started.wait(1)
        try:
            cache.revision += 1
            assert pipeline.request("frame", None, cache, 1)[0] == ["known-mask"]
            assert not pipeline.future.done()
        finally:
            release.set()
        pipeline.future.result(timeout=1)
        assert pipeline.request("frame", None, cache, 1)[0] == ["known-mask", "new-mask"]


def test_failure_of_current_ocr_is_not_hidden():
    import pytest
    def backend(image, settings, ocr, include_names=False, *, cache_only=False, cancelled=None):
        if cache_only:
            return [], {"pending": True}
        raise RuntimeError("OCR unavailable")
    with ThreadPoolExecutor(max_workers=1) as pool:
        pipeline = LatestFrameAnalyzer(pool, backend)
        pipeline.request("current", None, None, 1)
        with pytest.raises(RuntimeError, match="OCR unavailable"):
            pipeline.future.result(timeout=1)
        with pytest.raises(RuntimeError, match="OCR unavailable"):
            pipeline.request("current", None, None, 1)


def test_obsolete_ocr_timeout_does_not_remove_a_current_cached_preview():
    import pytest
    started, release = Event(), Event()
    def backend(image, settings, ocr, include_names=False, *, cache_only=False, cancelled=None):
        if cache_only:
            return (["current-mask"], {"pending": False}) if image == "new" else ([], {"pending": True})
        started.set()
        assert release.wait(2)
        raise RuntimeError("old frame timeout")
    with ThreadPoolExecutor(max_workers=1) as pool:
        pipeline = LatestFrameAnalyzer(pool, backend)
        pipeline.request("old", None, None, 1)
        assert started.wait(1)
        try:
            assert pipeline.request("new", None, None, 2)[0] == ["current-mask"]
        finally:
            release.set()
        with pytest.raises(RuntimeError):
            pipeline.future.result(timeout=1)
        assert pipeline.request("new", None, None, 2)[0] == ["current-mask"]
