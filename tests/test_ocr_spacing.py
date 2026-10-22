from kakao_filter.detector import join_ocr_words, Name, Rect, detect, analyze
from kakao_filter.config import Settings
from test_groups import group_scene, NamesByAvatar


def tokens(words, gaps):
    left = [0]
    for gap in gaps:
        left.append(left[-1] + 30 + gap)
    return {"text": words, "left": left, "width": [30]*len(words), "height": [36]*len(words)}


def test_close_hangul_syllables_do_not_invent_spaces():
    data = tokens(["정", "민", "욱"], [5, 6])
    assert join_ocr_words(data, [0, 1, 2]) == "정민욱"


def test_real_word_spacing_is_retained():
    data = tokens(["정민", "욱"], [15])
    assert join_ocr_words(data, [0, 1]) == "정민 욱"
    data = tokens(["Alice", "Smith"], [5])
    assert join_ocr_words(data, [0, 1]) == "Alice Smith"


def test_different_letters_never_fuzzy_match_and_optin_exposes_actual_names():
    class Misread(NamesByAvatar):
        def for_avatar(self, image, avatar):
            return [Name("정민룩", Rect(68, avatar.y, 40, 16), 93)] if avatar.y == 200 else super().for_avatar(image, avatar)
    settings = Settings(enabled=True, hiddenUsers=["정민욱"])
    image = group_scene()
    boxes, diagnostics = analyze(image, settings, Misread())
    assert boxes == []
    assert diagnostics == {"groups": 3, "matched": 0, "unreadable": 0}
    boxes, diagnostics = analyze(image, settings, Misread(), include_names=True)
    assert boxes == []
    assert diagnostics["readings"][1]["names"][0].text == "정민룩"
    assert len(diagnostics["readings"]) == 3
    settings.hiddenUsers.append("정민룩")  # Explicit user selection of an OCR alias.
    assert len(detect(image, settings, Misread())) == 3
