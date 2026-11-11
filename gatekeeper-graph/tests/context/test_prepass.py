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


def test_source_extension_does_not_eat_json_or_jsx() -> None:
    facts = prepass(
        "see package.json and src/main.jsx",
        frozenset({"src/main.jsx", "package.json"}),
    )
    assert facts.files == ("src/main.jsx",)


def test_windows_path_glued_to_a_node_stack() -> None:
    question = (
        r"node C:\Users\anilk\Desktop\coding\Visualize\sample-js\src\main.js"
        "node:internal/modules/cjs/loader:1568 Error: Cannot find module"
    )
    facts = prepass(question, frozenset({"src/main.js", "src/math.js"}))
    assert facts.files == ("src/main.js",)


def test_backslash_stripped_path_matches_a_repo_file() -> None:
    question = "Cannot find module UsersanilkDesktopcodingVisualizesample-jssrcmain.js"
    facts = prepass(question, frozenset({"src/main.js", "src/math.js"}))
    assert facts.files == ("src/main.js",)


def test_prose_has_no_files_frames_or_errors() -> None:
    facts = prepass("the receipt shows customer names in the wrong case")
    assert facts.files == ()
    assert facts.frames == ()
    assert facts.backticks == ()
    assert facts.error_types == ()
    assert facts.quoted == ()
