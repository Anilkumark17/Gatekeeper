"""Run R2 graph retrieval stage by stage from a fixed Intent. R1 is bypassed.

Usage:
  uv run python scripts/r2_probe.py GRAPH ROOT --phrases "receipt,customer names,case"
      [--type bug] [--confidence low] [--backtick lineFor] [--file src/receipt.js]
      [--frame src/receipt.js:4] [--expect src/utils/string.js#titleCase] [--llm] [--budget 3000]

Exit code 0 when every --expect id is in the final pack, 1 otherwise.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from gatekeeper_graph.context.budget import apply_budget, estimate_tokens
from gatekeeper_graph.context.expand import expand
from gatekeeper_graph.context.graph_index import GraphIndex
from gatekeeper_graph.context.intent import Confidence, Intent, ProblemType, StackFrame
from gatekeeper_graph.context.rank import rank
from gatekeeper_graph.context.search import load_or_build
from gatekeeper_graph.context.select import select
from gatekeeper_graph.context.shortlist import build_shortlist
from gatekeeper_graph.store import load_graph


def _frame(raw: str) -> StackFrame:
    file, _, line = raw.rpartition(":")
    return StackFrame(name="frame", file=file, line=int(line))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("graph", type=Path)
    parser.add_argument("root", type=Path)
    parser.add_argument("--phrases", default="")
    parser.add_argument("--observed")
    parser.add_argument("--type", default="bug", choices=[p.value for p in ProblemType])
    parser.add_argument("--confidence", default="low", choices=[c.value for c in Confidence])
    parser.add_argument("--backtick", action="append", default=[])
    parser.add_argument("--file", action="append", default=[])
    parser.add_argument("--frame", action="append", default=[])
    parser.add_argument("--expect", action="append", default=[])
    parser.add_argument("--llm", action="store_true", help="let Qwen select anchors")
    parser.add_argument("--budget", type=int, default=3000)
    args = parser.parse_args()

    phrases = tuple(p.strip() for p in args.phrases.split(",") if p.strip())
    intent = Intent(
        question=" ".join(phrases) or "probe",
        problem_type=ProblemType(args.type),
        observed=args.observed,
        key_phrases=phrases,
        backtick_names=tuple(args.backtick),
        files=tuple(args.file),
        frames=tuple(_frame(f) for f in args.frame),
        confidence=Confidence(args.confidence),
        source="llm" if args.llm else "rules",
    )
    graph = load_graph(args.graph)
    index = GraphIndex(graph)
    search = load_or_build(graph, args.graph, write=False)

    print("== 1 search hits per phrase")
    for phrase in phrases:
        hits = search.search(phrase, k=5)
        shown = ", ".join(f"{h.node_id.split('#')[-1]}={h.score:.2f}" for h in hits)
        print(f"  {phrase!r}: {shown}")

    shortlist = build_shortlist(intent, index, search)
    print(f"== 2 shortlist ({len(shortlist)})")
    for c in shortlist:
        print(f"  {'PIN ' if c.pinned else '    '}{c.score:.2f} {c.node_id} {sorted(c.sources)}")

    client = None
    if args.llm:
        from gatekeeper_graph.llm import make_client

        client = make_client()
    else:
        from gatekeeper_graph.llm.fake import FakeClient

        client = FakeClient([], available=False)
    selection = select(intent, shortlist, index, client, "llm" if args.llm else "rules")
    print(f"== 3 anchors ({len(selection.anchors)}) fallback={selection.fallback_reason}")
    for a in selection.anchors:
        print(f"  {a.via:6} {a.node_id}  {a.reason}")

    expansion, gaps = expand(
        intent.problem_type, intent.confidence, [a.node_id for a in selection.anchors], index
    )
    print(f"== 4 expansion ({len(expansion.nodes)}) gaps={[g.kind for g in gaps]}")
    for node_id, r in sorted(expansion.nodes.items(), key=lambda kv: (kv[1].hops, kv[0])):
        if r.direction in ("self", "upstream", "downstream"):
            print(f"  hop{r.hops} {r.direction:10} via={r.via_edge_type} {node_id} <- {r.parent}")

    ranked = rank(intent, list(selection.anchors), shortlist, expansion, index, set())
    print(f"== 5 ranked ({len(ranked)})")
    for item in ranked[:15]:
        print(f"  {item.score:.3f} {item.role:10} {item.node_id}")

    ranges = {}
    for item in ranked:
        node = index.get(item.node_id)
        if node is not None and node.file is not None and node.range is not None:
            ranges[item.node_id] = (node.file, node.range.start, node.range.end)
    required = {a.node_id for a in selection.anchors}
    kept, dropped, used = apply_budget(
        ranked,
        args.root,
        ranges,
        limit=args.budget,
        overhead=estimate_tokens(intent.model_dump_json()) + 200,
        required=required,
    )
    kept_ids = {k.node_id for k in kept}
    print(f"== 6 budget used={used}/{args.budget} kept={len(kept)} dropped={len(dropped)}")

    missing = [e for e in args.expect if e not in kept_ids]
    for e in args.expect:
        print(f"  expect {e}: {'IN PACK' if e in kept_ids else 'MISSING'}")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
