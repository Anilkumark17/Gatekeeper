import importlib

MODULES = [
    "gatekeeper_graph",
    "gatekeeper_graph.models",
    "gatekeeper_graph.resolver",
    "gatekeeper_graph.builder",
    "gatekeeper_graph.incremental",
    "gatekeeper_graph.reverse_index",
    "gatekeeper_graph.summarizer",
    "gatekeeper_graph.watcher",
    "gatekeeper_graph.store",
    "gatekeeper_graph.cli",
    "gatekeeper_graph.parser",
]


def test_all_modules_import() -> None:
    for name in MODULES:
        importlib.import_module(name)
