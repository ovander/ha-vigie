"""Every user-visible string exists in strings.json, en.json and fr.json (CLAUDE.md)."""

import json
from pathlib import Path

import pytest

BASE = Path(__file__).parent.parent / "custom_components" / "vigie"


def _load(name: str) -> dict:
    return json.loads((BASE / name).read_text(encoding="utf-8"))


def _keys(tree: dict, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    for key, value in tree.items():
        path = f"{prefix}.{key}" if prefix else key
        keys |= _keys(value, path) if isinstance(value, dict) else {path}
    return keys


def test_english_translation_matches_strings():
    assert _load("translations/en.json") == _load("strings.json")


def test_french_translation_has_the_same_keys():
    assert _keys(_load("translations/fr.json")) == _keys(_load("strings.json"))


@pytest.mark.parametrize("name", ["strings.json", "translations/en.json", "translations/fr.json"])
def test_no_empty_strings(name):
    def walk(tree):
        for value in tree.values():
            if isinstance(value, dict):
                yield from walk(value)
            else:
                yield value

    assert all(isinstance(v, str) and v.strip() for v in walk(_load(name)))
