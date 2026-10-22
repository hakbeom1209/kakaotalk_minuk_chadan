import json
import pytest
from kakao_filter.config import Settings, load, save


def test_settings_round_trip_and_scope(tmp_path):
    path = tmp_path / "settings.json"
    settings = Settings.parse({"enabled": True, "hiddenUsers": [" 민욱 ", "민욱", ""], "selectedChats": ["개발방"]})
    save(path, settings)
    assert load(path) == settings
    assert settings.hiddenUsers == ["민욱"]
    assert settings.applies("개발방")
    assert not settings.applies("다른방")
    settings.chatScope = "all"
    assert settings.applies("다른방")
    settings.enabled = False
    assert not settings.applies("개발방")


@pytest.mark.parametrize("raw", [[], {"enabled": "false"}, {"hiddenUsers": "민욱"},
    {"hiddenUsers": [1]}, {"displayMode": "invalid"}, {"intervalMs": 0},
    {"topMargin": True}, {"ocrLanguage": "unknown"}])
def test_invalid_settings_rejected(raw):
    with pytest.raises(ValueError):
        Settings.parse(raw)


def test_bad_save_preserves_previous_file(tmp_path):
    path = tmp_path / "settings.json"
    save(path, Settings())
    previous = path.read_bytes()
    with pytest.raises(ValueError):
        save(path, Settings(displayMode="bad"))
    assert path.read_bytes() == previous
    assert len(list(tmp_path.iterdir())) == 1


def test_missing_and_malformed_settings(tmp_path):
    path = tmp_path / "settings.json"
    assert not load(path).enabled
    path.write_text("{", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        load(path)
    assert path.read_text() == "{"
