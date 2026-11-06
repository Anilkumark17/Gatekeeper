import pytest

from gatekeeper_graph.parser.languages import LanguageId, get_language, language_for_path


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("a.js", LanguageId.JAVASCRIPT),
        ("src/App.JS", LanguageId.JAVASCRIPT),
        ("src\\widget.jsx", LanguageId.JAVASCRIPT),
        ("lib/mod.mjs", LanguageId.JAVASCRIPT),
        ("lib/mod.cjs", LanguageId.JAVASCRIPT),
        ("a.ts", LanguageId.TYPESCRIPT),
        ("src/types.mts", LanguageId.TYPESCRIPT),
        ("src/types.cts", LanguageId.TYPESCRIPT),
        ("SRC/APP.TS", LanguageId.TYPESCRIPT),
        ("a.tsx", LanguageId.TSX),
        ("components/Button.TSX", LanguageId.TSX),
        ("types.d.ts", None),
        ("src/types.D.TS", None),
        ("src/app.css", None),
        ("package.json", None),
        ("Makefile", None),
        ("src/README", None),
        ("", None),
    ],
)
def test_language_for_path(path: str, expected: LanguageId | None) -> None:
    assert language_for_path(path) is expected


def test_get_language_is_cached() -> None:
    for lang in LanguageId:
        assert get_language(lang) is get_language(lang)
