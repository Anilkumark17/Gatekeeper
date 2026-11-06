"""Extract symbols, imports, exports, and calls from one parsed file."""

from __future__ import annotations

import hashlib
import logging

from tree_sitter import Node

from gatekeeper_graph.extractor.types import (
    CallRef,
    ExportRef,
    FileExtraction,
    FlowRef,
    ImportedName,
    ImportKind,
    ImportRef,
    ReferenceRef,
)
from gatekeeper_graph.models import (
    Edge,
    EdgeType,
    Evidence,
    LineRange,
    NodeKind,
    Signature,
    make_module_id,
)
from gatekeeper_graph.models import Node as GraphNode
from gatekeeper_graph.parser.core import ParsedFile
from gatekeeper_graph.parser.nodes import end_line_of, field_text, find_all, line_of, text_of

logger = logging.getLogger(__name__)


def extract_file(parsed: ParsedFile) -> FileExtraction:
    """Return every fact that can be known without looking at other files."""
    symbols = _symbols(parsed)
    nodes = [
        _file_node(parsed),
        _module_node(parsed),
        *(_symbol_node(parsed, item) for item in symbols),
    ]
    contains = (
        _module_contains(parsed.path),
        *(_contains_edge(parsed.path, item) for item in symbols),
    )
    logger.info("extracted path=%s symbols=%s", parsed.path, len(symbols))
    return FileExtraction(
        path=parsed.path,
        nodes=tuple(nodes),
        contains=contains,
        imports=_imports(parsed, symbols),
        exports=_exports(parsed),
        calls=_calls(parsed, symbols),
        references=_references(parsed, symbols),
        flows=_flows(parsed),
    )


class _Symbol:
    def __init__(self, name: str, node: Node, kind: NodeKind, params: tuple[str, ...]) -> None:
        self.name = name
        self.node = node
        self.kind = kind
        self.params = params


def _symbols(parsed: ParsedFile) -> list[_Symbol]:
    found: list[_Symbol] = []
    for child in parsed.root.named_children:
        if child.type == "export_statement":
            declaration = child.child_by_field_name("declaration")
            if declaration is not None:
                found.extend(_declaration_symbols(parsed, declaration))
            continue
        found.extend(_declaration_symbols(parsed, child))
    return found


def _declaration_symbols(parsed: ParsedFile, node: Node) -> list[_Symbol]:
    if node.type == "function_declaration":
        name = field_text(node, "name", parsed.source)
        if name is None:
            return []
        return [_Symbol(name, node, _kind(name, node, parsed), _params(node, parsed))]
    if node.type == "class_declaration":
        name = field_text(node, "name", parsed.source)
        if name is None:
            return []
        return [_Symbol(name, node, _kind(name, node, parsed), ())]
    if node.type not in {"lexical_declaration", "variable_declaration"}:
        return []
    symbols: list[_Symbol] = []
    for declarator in node.named_children:
        if declarator.type != "variable_declarator":
            continue
        name = field_text(declarator, "name", parsed.source)
        if name is None:
            continue
        value = declarator.child_by_field_name("value")
        kind = _kind(name, value if value is not None else declarator, parsed)
        params = _params(value, parsed) if value is not None else ()
        symbols.append(_Symbol(name, declarator, kind, params))
    return symbols


def _kind(name: str, node: Node, parsed: ParsedFile) -> NodeKind:
    function_like = node.type in {"function_declaration", "arrow_function", "function"}
    if _is_hook(name) and function_like:
        return NodeKind.HOOK
    if function_like and _is_component_name(name) and _contains_jsx(node):
        return NodeKind.COMPONENT
    if function_like:
        return NodeKind.FUNCTION
    if node.type == "class_declaration" and _contains_jsx(node):
        return NodeKind.COMPONENT
    return NodeKind.CONSTANT


def _is_hook(name: str) -> bool:
    return len(name) > 3 and name.startswith("use") and name[3].isupper()


def _is_component_name(name: str) -> bool:
    return name[:1].isupper() and not name.isupper()


def _contains_jsx(node: Node) -> bool:
    return any(
        item.type in {"jsx_element", "jsx_self_closing_element", "jsx_fragment"}
        for item in find_all(node, "jsx_element", "jsx_self_closing_element", "jsx_fragment")
    )


def _named(node: Node, kind: str) -> Node | None:
    return next((child for child in node.named_children if child.type == kind), None)


def _identifiers(node: Node, source: bytes) -> list[str]:
    return [text_of(child, source) for child in node.named_children if child.type == "identifier"]


def _params(node: Node, parsed: ParsedFile) -> tuple[str, ...]:
    parameters = node.child_by_field_name("parameters")
    if parameters is None:
        return ()
    return tuple(_identifiers(parameters, parsed.source))


def _file_node(parsed: ParsedFile) -> GraphNode:
    return GraphNode(
        id=parsed.path,
        kind=NodeKind.FILE,
        file=parsed.path,
        hash=_file_hash(parsed.source),
        tokens=_tokens(parsed.root, parsed.source),
        literals=_literals(parsed.root, parsed.source),
    )


def _module_node(parsed: ParsedFile) -> GraphNode:
    text = parsed.source.decode("utf-8", errors="replace")
    line_count = max(len(text.splitlines()), 1)
    return GraphNode(
        id=make_module_id(parsed.path),
        kind=NodeKind.MODULE,
        file=parsed.path,
        range=LineRange(start=1, end=line_count),
        hash=_file_hash(parsed.source),
        tokens=_tokens(parsed.root, parsed.source),
        literals=_literals(parsed.root, parsed.source),
    )


def _module_contains(path: str) -> Edge:
    return Edge(
        source=make_module_id(path),
        target=path,
        type=EdgeType.CONTAINS,
        evidence=Evidence(file=path, line=1),
    )


def _symbol_node(parsed: ParsedFile, symbol: _Symbol) -> GraphNode:
    return GraphNode(
        id=f"{parsed.path}#{symbol.name}",
        kind=symbol.kind,
        file=parsed.path,
        range=LineRange(start=line_of(symbol.node), end=end_line_of(symbol.node)),
        hash=_hash(symbol.node, parsed.source),
        signature=Signature(params=symbol.params),
        tokens=_tokens(symbol.node, parsed.source),
        literals=_literals(symbol.node, parsed.source),
    )


def _contains_edge(path: str, symbol: _Symbol) -> Edge:
    return Edge(
        source=path,
        target=f"{path}#{symbol.name}",
        type=EdgeType.CONTAINS,
        evidence=Evidence(file=path, line=line_of(symbol.node)),
    )


def _hash(node: Node, source: bytes) -> str:
    return _file_hash(text_of(node, source).encode("utf-8"))


def _file_hash(source: bytes) -> str:
    text = source.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    normalized = "\n".join(line.rstrip() for line in text.split("\n"))
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def _tokens(node: Node, source: bytes) -> tuple[str, ...]:
    names = [
        text_of(item, source)
        for item in find_all(node, "identifier", "property_identifier")
        if text_of(item, source).isidentifier()
    ]
    return tuple(sorted(set(names)))


def _literals(node: Node, source: bytes) -> tuple[str, ...]:
    found: list[str] = []
    for item in find_all(node, "string", "number", "template_string"):
        fragments = [
            text_of(child, source)
            for child in item.named_children
            if child.type == "string_fragment"
        ]
        if fragments:
            found.extend(fragments)
        elif item.type == "number":
            found.append(text_of(item, source))
    return tuple(sorted(set(found)))


def _imports(parsed: ParsedFile, symbols: list[_Symbol]) -> tuple[ImportRef, ...]:
    refs: list[ImportRef] = []
    for statement in parsed.root.named_children:
        if statement.type != "import_statement":
            continue
        source = statement.child_by_field_name("source")
        if source is None:
            continue
        specifier = _specifier(source, parsed.source)
        clause = _named(statement, "import_clause")
        refs.append(_static_import(parsed.path, specifier, line_of(statement), clause, parsed))
    for call in find_all(parsed.root, "call_expression"):
        function = call.named_children[0] if call.named_children else None
        if function is None or function.type != "import":
            continue
        arguments = call.child_by_field_name("arguments")
        if arguments is None:
            continue
        string_node = _named(arguments, "string")
        if string_node is None:
            continue
        refs.append(
            ImportRef(
                specifier=_specifier(string_node, parsed.source),
                kind=ImportKind.DYNAMIC,
                line=line_of(call),
                owner=_owner(call, parsed.path, symbols),
            )
        )
    return tuple(refs)


def _static_import(
    path: str,
    specifier: str,
    line: int,
    clause: Node | None,
    parsed: ParsedFile,
) -> ImportRef:
    if clause is None:
        return ImportRef(specifier=specifier, kind=ImportKind.SIDE_EFFECT, line=line, owner=path)
    namespace = _named(clause, "namespace_import")
    if namespace is not None:
        local = field_text(namespace, "name", parsed.source) or "*"
        return ImportRef(
            specifier=specifier,
            kind=ImportKind.NAMESPACE,
            names=(ImportedName(imported="*", local=local),),
            line=line,
            owner=path,
        )
    named = [
        child for child in find_all(clause, "import_specifier") if _encloses(clause, child)
    ]
    if named:
        return ImportRef(
            specifier=specifier,
            kind=ImportKind.NAMED,
            names=tuple(_imported_name(item, parsed) for item in named),
            line=line,
            owner=path,
        )
    names = _identifiers(clause, parsed.source)
    default_name = names[0] if names else None
    if default_name is not None:
        return ImportRef(
            specifier=specifier,
            kind=ImportKind.DEFAULT,
            names=(ImportedName(imported="default", local=default_name),),
            line=line,
            owner=path,
        )
    return ImportRef(specifier=specifier, kind=ImportKind.SIDE_EFFECT, line=line, owner=path)


def _imported_name(specifier: Node, parsed: ParsedFile) -> ImportedName:
    name = field_text(specifier, "name", parsed.source)
    alias = field_text(specifier, "alias", parsed.source)
    if name is None:
        identifiers = _identifiers(specifier, parsed.source)
        name = identifiers[0] if identifiers else text_of(specifier, parsed.source)
        alias = identifiers[1] if len(identifiers) > 1 else None
    return ImportedName(imported=name, local=alias or name)


def _exports(parsed: ParsedFile) -> tuple[ExportRef, ...]:
    refs: list[ExportRef] = []
    for statement in parsed.root.named_children:
        if statement.type != "export_statement":
            continue
        source = statement.child_by_field_name("source")
        specifier = _specifier(source, parsed.source) if source is not None else None
        declaration = statement.child_by_field_name("declaration")
        if declaration is not None:
            for symbol in _declaration_symbols(parsed, declaration):
                refs.append(
                    ExportRef(exported=symbol.name, local=symbol.name, line=line_of(statement))
                )
            continue
        clause = _named(statement, "export_clause")
        star = any(text_of(child, parsed.source) == "*" for child in statement.children)
        if clause is None and star:
            refs.append(
                ExportRef(
                    exported="*",
                    local=None,
                    line=line_of(statement),
                    from_specifier=specifier,
                    is_star=True,
                )
            )
            continue
        if clause is None:
            continue
        for specifier_node in clause.named_children:
            if specifier_node.type != "export_specifier":
                continue
            name = field_text(specifier_node, "name", parsed.source)
            alias = field_text(specifier_node, "alias", parsed.source)
            if name is None:
                identifiers = [
                    text_of(child, parsed.source)
                    for child in specifier_node.named_children
                    if child.type == "identifier"
                ]
                name = identifiers[0] if identifiers else None
                alias = identifiers[1] if len(identifiers) > 1 else None
            if name is None:
                continue
            refs.append(
                ExportRef(
                    exported=alias or name,
                    local=name,
                    line=line_of(statement),
                    from_specifier=specifier,
                )
            )
    return tuple(refs)


def _calls(parsed: ParsedFile, symbols: list[_Symbol]) -> tuple[CallRef, ...]:
    refs: list[CallRef] = []
    for call in find_all(parsed.root, "call_expression"):
        function = call.named_children[0] if call.named_children else None
        if function is None or function.type == "import":
            continue
        if function.type == "identifier" or function.type == "member_expression":
            callee = text_of(function, parsed.source)
        else:
            continue
        refs.append(
            CallRef(
                owner=_owner(call, parsed.path, symbols),
                callee=callee,
                line=line_of(call),
                args=_call_args(call, parsed.source),
            )
        )
    return tuple(refs)


def _call_args(call: Node, source: bytes) -> tuple[str, ...]:
    arguments = call.child_by_field_name("arguments")
    if arguments is None:
        return ()
    return tuple(text_of(child, source) for child in arguments.named_children)


def _references(parsed: ParsedFile, symbols: list[_Symbol]) -> tuple[ReferenceRef, ...]:
    refs: list[ReferenceRef] = []
    for ident in find_all(parsed.root, "identifier"):
        if _in_import_or_export_clause(ident):
            continue
        if _is_callee(ident) or _is_declared_name(ident):
            continue
        name = text_of(ident, parsed.source)
        if not name.isidentifier():
            continue
        refs.append(
            ReferenceRef(owner=_owner(ident, parsed.path, symbols), name=name, line=line_of(ident))
        )
    return tuple(refs)


def _flows(parsed: ParsedFile) -> tuple[FlowRef, ...]:
    refs: list[FlowRef] = []
    for call in find_all(parsed.root, "call_expression"):
        function = call.named_children[0] if call.named_children else None
        if function is None or function.type not in {"identifier", "member_expression"}:
            continue
        target = text_of(function, parsed.source).split(".", 1)[0]
        arguments = call.child_by_field_name("arguments")
        if arguments is None:
            continue
        for child in arguments.named_children:
            if child.type != "identifier":
                continue
            refs.append(
                FlowRef(
                    source_name=text_of(child, parsed.source),
                    target_name=target,
                    line=line_of(child),
                )
            )
    for declarator in find_all(parsed.root, "variable_declarator"):
        name = field_text(declarator, "name", parsed.source)
        value = declarator.child_by_field_name("value")
        if name is None or value is None:
            continue
        source_name = _flow_source(value, parsed.source)
        if source_name is None:
            continue
        refs.append(FlowRef(source_name=source_name, target_name=name, line=line_of(declarator)))
    return tuple(refs)


def _flow_source(value: Node, source: bytes) -> str | None:
    if value.type == "identifier":
        return text_of(value, source)
    if value.type == "call_expression" and value.named_children:
        function = value.named_children[0]
        if function.type in {"identifier", "member_expression"}:
            return text_of(function, source).split(".", 1)[0]
    return None


def _in_import_or_export_clause(node: Node) -> bool:
    current = node.parent
    while current is not None:
        if current.type in {"import_statement", "export_statement"}:
            declaration = current.child_by_field_name("declaration")
            return not (declaration is not None and _encloses(declaration, node))
        current = current.parent
    return False


def _is_callee(node: Node) -> bool:
    parent = node.parent
    if parent is None or parent.type != "call_expression" or not parent.named_children:
        return False
    return parent.named_children[0] == node


def _is_declared_name(node: Node) -> bool:
    parent = node.parent
    if parent is None:
        return False
    return parent.child_by_field_name("name") == node


def _owner(node: Node, path: str, symbols: list[_Symbol]) -> str:
    match = [
        symbol
        for symbol in symbols
        if symbol.node.start_byte <= node.start_byte and node.end_byte <= symbol.node.end_byte
    ]
    if not match:
        return path
    chosen = min(match, key=lambda symbol: symbol.node.end_byte - symbol.node.start_byte)
    return f"{path}#{chosen.name}"


def _specifier(node: Node, source: bytes) -> str:
    fragments = [item for item in find_all(node, "string_fragment") if item != node]
    if fragments:
        return text_of(fragments[0], source)
    return text_of(node, source).strip("\"'`")


def _encloses(parent: Node, child: Node) -> bool:
    return parent.start_byte <= child.start_byte and child.end_byte <= parent.end_byte
