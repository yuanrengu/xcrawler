from __future__ import annotations

import importlib.util


def modules_available(*module_names: str) -> bool:
    return all(importlib.util.find_spec(module_name) is not None for module_name in module_names)


def print_missing_optional_dependency(package: str, extra: str, *, feature: str) -> None:
    """Print a consistent, actionable error for an unavailable optional dependency."""
    print(f"❌ {feature}需要可选依赖 {package}。")
    print(f"   请运行: python3 -m pip install -e '.[{extra}]'")
