"""Runtime loader for the split bizinfo collector modules.

The original script was split into ordered part files to improve readability
while preserving the existing global execution model.
"""

from pathlib import Path

PART_FILES = [
    "00_config_keywords_headers.py",
    "01_common.py",
    "02_sheets.py",
    "03_logging_driver_row.py",
    "04_bizinfo.py",
    "05_iris.py",
    "06_smart_factory.py",
    "08_ministry_boards.py",
    "07_dedupe_runner.py",
]

_NAMESPACE = None


def load_namespace(force_reload=False):
    """Load all split part files into one shared namespace."""
    global _NAMESPACE

    if _NAMESPACE is not None and not force_reload:
        return _NAMESPACE

    base_dir = Path(__file__).resolve().parent
    parts_dir = base_dir / "parts"
    namespace = {
        "__name__": "bizinfo_collector.runtime_namespace",
        "__file__": str(base_dir / "parts" / "00_config_keywords_headers.py"),
    }

    for part_name in PART_FILES:
        part_path = parts_dir / part_name
        code = part_path.read_text(encoding="utf-8-sig")
        exec(compile(code, str(part_path), "exec"), namespace)

    _NAMESPACE = namespace
    return namespace


def run():
    """Run the collector."""
    namespace = load_namespace()
    return namespace["run"]()
