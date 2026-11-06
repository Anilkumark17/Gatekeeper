from gatekeeper_graph.context.prepass import prepass

_FILES = frozenset({"src/receipt.js", "src/main.js", "lib/receipt.js"})


def test_quotes_backticks_and_errors() -> None:
    facts = prepass('it says "too high" and \'daily total\' plus `titleCase` and a TypeError')
    assert facts.quoted == ("too high", "daily total")
    assert facts.backticks == ("titleCase",)
    assert facts.error_types == ("TypeError",)


def test_quotes_inside_backticks_are_not_quoted() -> None:
    facts = prepass('use `"keep"` as the token and "ok"')
    assert facts.quoted == ("ok",)
    assert facts.backticks == ('"keep"',)


def test_partial_path_and_ambiguous_suffix() -> None:
    unique = prepass("see receipt.js please", frozenset({"src/receipt.js", "src/main.js"}))
    assert unique.files == ("src/receipt.js",)
    ambiguous = prepass("see receipt.js please", _FILES)
    assert ambiguous.files == ()


def test_windows_frame_and_plain_frame() -> None:
    question = r"at lineFor (C:\Users\anilk\proj\src\receipt.js:4:1)"
    facts = prepass(question, frozenset({"src/receipt.js"}))
    assert len(facts.frames) == 1
    assert facts.frames[0].name == "lineFor"
    assert facts.frames[0].file == "src/receipt.js"
    assert facts.frames[0].line == 4
    plain = prepass("at src/main.js:10:3", frozenset({"src/main.js"}))
    assert plain.frames[0].name == ""
    assert plain.frames[0].file == "src/main.js"
    assert plain.frames[0].line == 10


def test_prose_has_no_files_frames_or_errors() -> None:
    facts = prepass("the receipt shows customer names in the wrong case")
    assert facts.files == ()
    assert facts.frames == ()
    assert facts.backticks == ()
    assert facts.error_types == ()
    assert facts.quoted == ()
