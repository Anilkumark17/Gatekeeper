"""Hand a context pack to the diagnosis agent. The default handler stores the pack."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from gatekeeper_graph.context.pack import ContextPack

logger = logging.getLogger(__name__)

DiagnosisHandler = Callable[[ContextPack], None]
_HANDLERS: list[DiagnosisHandler] = []


def register_handler(handler: DiagnosisHandler) -> None:
    """The diagnosis agent registers itself here later."""
    _HANDLERS.append(handler)


def clear_handlers() -> None:
    """Drop registered handlers. Tests use this."""
    _HANDLERS.clear()


def send_to_diagnosis(pack: ContextPack, graph_path: Path) -> Path:
    """Call registered handlers, or write packs/<timestamp>.pack.json beside the graph."""
    destination = _pack_path(graph_path)
    if _HANDLERS:
        for handler in _HANDLERS:
            handler(pack)
        logger.info("context handoff handlers=%s path=%s", len(_HANDLERS), destination)
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(pack.model_dump_json(indent=2, by_alias=True) + "\n", encoding="utf-8")
    logger.info("context handoff path=%s", destination)
    return destination


def _pack_path(graph_path: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return graph_path.parent / "packs" / f"{stamp}.pack.json"
