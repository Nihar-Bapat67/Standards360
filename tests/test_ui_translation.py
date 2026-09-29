import html
from types import SimpleNamespace

import pytest

from app import ui_translation


class TranslationResponse:
    def __init__(self, values):
        self.values = values

    def raise_for_status(self):
        pass

    def json(self):
        return {
            "data": {
                "translations": [
                    {"translatedText": html.escape(value, quote=False)} for value in self.values
                ]
            }
        }


def test_dictionary_translation_preserves_interpolation_and_is_cached(monkeypatch):
    monkeypatch.setattr(ui_translation, "_CACHE", {})
    monkeypatch.setattr(ui_translation, "settings", SimpleNamespace(google_translate_api_key="test-key"))
    english = ui_translation._english_dictionary()
    english["test.interpolation"] = "Keep {name}, BIS and IS 269:2015."
    monkeypatch.setattr(ui_translation, "_english_dictionary", lambda: english)
    calls = []

    def translate(url, *, params, json, timeout):
        calls.append((params, json, timeout))
        return TranslationResponse(json["q"])

    monkeypatch.setattr(ui_translation.requests, "post", translate)

    dictionary = ui_translation.translate_ui_dictionary("od")

    assert dictionary["landing.intro"] == english["landing.intro"]
    assert dictionary["test.interpolation"] == english["test.interpolation"]
    assert "app.name" not in dictionary
    assert calls[0][1]["target"] == "or"
    assert ui_translation.translate_ui_dictionary("od") is dictionary
    assert len(calls) == (len(english) + 99) // 100


def test_dictionary_translation_requires_a_key(monkeypatch):
    monkeypatch.setattr(ui_translation, "settings", SimpleNamespace(google_translate_api_key=None))

    with pytest.raises(ui_translation.UITranslationUnavailable):
        ui_translation.translate_ui_dictionary("hi")

    with pytest.raises(ValueError):
        ui_translation.translate_ui_dictionary("xx")