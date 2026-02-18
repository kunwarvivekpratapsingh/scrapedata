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

# Modules that LLM-generated user code must NEVER be allowed to import.
# Note: internal C-extension modules like _strptime, _datetime, _statistics
# are intentionally NOT blocked — Python's standard library calls them
# transparently during lazy initialisation (e.g. first call to strptime).
BLOCKED_IMPORT_MODULES: set[str] = {
    "os", "sys", "subprocess", "socket", "pickle", "importlib",
    "ctypes", "threading", "multiprocessing", "shutil", "pathlib",
    "io", "pty", "atexit", "signal", "gc", "inspect", "dis",
    "ast", "code", "codeop", "compileall", "py_compile", "builtins",
    "site", "sysconfig", "platform", "struct", "mmap",
}

FORBIDDEN_BUILTINS: set[str] = {
    # __import__ is NOT in this set — see build_restricted_builtins() for why
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


def _make_safe_import(original_import):
    """Return a restricted __import__ that blocks dangerous modules.

    Why we need this: Python's C-level standard library (datetime.strptime,
    statistics.stdev, re.compile, etc.) performs lazy internal imports of
    private C-extension modules like _strptime, _datetime, _statistics on
    first use. When __builtins__ is a plain dict with no __import__ key,
    these lazy imports raise KeyError: '__import__', breaking stdlib calls
    even though the LLM code contains no import statements.

    The fix: include a safe __import__ that ALLOWS internal/stdlib lazy
    imports but BLOCKS any top-level user-facing dangerous modules.
    """
    def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
        top_level = name.split(".")[0]
        if top_level in BLOCKED_IMPORT_MODULES:
            raise ImportError(
                f"Import of '{name}' is not allowed in the sandbox. "
                f"Use the pre-loaded module variables instead."
            )
        return original_import(name, globals, locals, fromlist, level)
    return safe_import


def build_restricted_builtins() -> dict:
    """Build a restricted __builtins__ dict for sandbox execution.

    Includes a safe __import__ so that Python's stdlib C-extensions can
    perform their internal lazy imports (e.g. _strptime for datetime.strptime)
    without allowing user code to import dangerous modules like os or sys.
    """
    import builtins as _builtins

    restricted = {}
    for name in SAFE_BUILTINS:
        if hasattr(_builtins, name):
            restricted[name] = getattr(_builtins, name)

    # Add None, True, False explicitly
    restricted["None"] = None
    restricted["True"] = True
    restricted["False"] = False

    # Add exception types so node code can raise/catch them
    for exc_name in ("ValueError", "TypeError", "KeyError", "IndexError",
                     "AttributeError", "StopIteration", "ZeroDivisionError",
                     "RuntimeError", "Exception", "BaseException",
                     "NotImplementedError", "OverflowError"):
        if hasattr(_builtins, exc_name):
            restricted[exc_name] = getattr(_builtins, exc_name)

    # CRITICAL: include a safe __import__ to allow stdlib C-extension lazy
    # imports (like _strptime) while blocking dangerous user imports.
    restricted["__import__"] = _make_safe_import(_builtins.__import__)

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
