from __future__ import annotations


def print_missing_optional_dependency(package: str, extra: str, *, feature: str) -> None:
    """Print a consistent, actionable error for an unavailable optional dependency."""
    print(f"❌ {feature}需要可选依赖 {package}。")
    print(f"   请运行: python3 -m pip install -e '.[{extra}]'")
