"""Cross-file resolution."""

from gatekeeper_graph.resolver.config import ResolverConfig, load_config
from gatekeeper_graph.resolver.core import resolve_all, resolve_specifier

__all__ = ["ResolverConfig", "load_config", "resolve_all", "resolve_specifier"]
