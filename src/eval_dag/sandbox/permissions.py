"""Sandbox permission configuration.

Defines which builtins and modules are allowed when executing
LLM-generated code in the sandbox.
"""

from __future__ import annotations

SAFE_BUILTINS: set[str] = {
    "abs",
    "all",
    "any",
    "bin",
    "bool",
    "bytes",
    "callable",
    "chr",
    "complex",
    "dict",
    "divmod",
    "enumerate",
    "filter",
    "float",
    "format",
    "frozenset",
    "hash",
    "hex",
    "int",
    "isinstance",
    "issubclass",
    "iter",
    "len",
    "list",
    "map",
    "max",
    "min",
    "next",
    "oct",
    "ord",
    "pow",
    "print",
    "range",
    "repr",
    "reversed",
    "round",
    "set",
    "slice",
    "sorted",
    "str",
    "sum",
    "tuple",
    "type",
    "zip",
}

SAFE_MODULES: set[str] = {
    "math",
    "statistics",
    "collections",
    "itertools",
    "functools",
    "json",
    "re",
    "datetime",
    "decimal",
    "fractions",
    "operator",
    "string",
    "textwrap",
    "copy",
    "numbers",
    "random",
}

FORBIDDEN_BUILTINS: set[str] = {
    "__import__",
    "exec",
    "eval",
    "compile",
    "globals",
    "locals",
    "vars",
    "dir",
    "getattr",
    "setattr",
    "delattr",
    "open",
    "input",
    "breakpoint",
    "exit",
    "quit",
    "memoryview",
    "classmethod",
    "staticmethod",
    "property",
    "super",
}


def build_restricted_builtins() -> dict:
    """Build a restricted __builtins__ dict for sandbox execution."""
    import builtins

    restricted = {}
    for name in SAFE_BUILTINS:
        if hasattr(builtins, name):
            restricted[name] = getattr(builtins, name)

    # Add None, True, False explicitly
    restricted["None"] = None
    restricted["True"] = True
    restricted["False"] = False

    return restricted


def build_safe_module_imports() -> dict:
    """Pre-import safe modules and return them as a dict."""
    import importlib

    modules = {}
    for mod_name in SAFE_MODULES:
        try:
            modules[mod_name] = importlib.import_module(mod_name)
        except ImportError:
            pass  # Module not available, skip
    return modules
