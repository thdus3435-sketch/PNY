"""Small entrypoint for the split bizinfo collector.

The implementation lives under `bizinfo_collector/parts`, grouped by domain.
Use this file the same way as before: `python bizinfo_datalist.py`.
"""

import os
import sys

from bizinfo_collector.runtime import load_namespace, run

_namespace = None


def _loaded_namespace():
    global _namespace
    if _namespace is None:
        _namespace = load_namespace()
    return _namespace


def __getattr__(name):
    namespace = _loaded_namespace()
    if name in namespace:
        return namespace[name]
    raise AttributeError(name)


if __name__ == "__main__":
    if "--reset-test-sheets" in sys.argv or os.getenv("BIZINFO_RESET_TEST_SHEETS") == "1":
        _loaded_namespace()["clear_test_run_sheets"]()

    run()
