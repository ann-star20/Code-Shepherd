"""Test-only fallbacks for optional runtime dependencies.

The project code imports infrastructure libraries at module import time, but unit
tests in a fresh local environment should still collect without a live DB stack.
"""

from __future__ import annotations

import sys
import types
from importlib.util import find_spec
from unittest.mock import MagicMock


if find_spec("asyncpg") is None and "asyncpg" not in sys.modules:
    asyncpg = types.ModuleType("asyncpg")
    asyncpg.Pool = object
    asyncpg.Connection = object
    asyncpg.PostgresConnectionError = Exception
    sys.modules["asyncpg"] = asyncpg


if find_spec("langchain_google_genai") is None and "langchain_google_genai" not in sys.modules:
    _lggl = types.ModuleType("langchain_google_genai")
    _lggl.ChatGoogleGenerativeAI = MagicMock()
    sys.modules["langchain_google_genai"] = _lggl


if find_spec("langgraph") is None and "langgraph" not in sys.modules:
    langgraph = types.ModuleType("langgraph")
    graph_module = types.ModuleType("langgraph.graph")

    class StateGraph:
        def __init__(self, *_args, **_kwargs):
            self.nodes = {}

        def add_node(self, name, fn):
            self.nodes[name] = fn

        def set_entry_point(self, _name):
            return None

        def add_edge(self, *_args, **_kwargs):
            return None

        def add_conditional_edges(self, *_args, **_kwargs):
            return None

        def compile(self):
            return self

    graph_module.StateGraph = StateGraph
    graph_module.END = "__end__"
    langgraph.graph = graph_module
    sys.modules["langgraph"] = langgraph
    sys.modules["langgraph.graph"] = graph_module
