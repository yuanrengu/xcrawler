from __future__ import annotations

import argparse


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("必须是大于等于 1 的整数")
    return parsed


def non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("必须是大于等于 0 的整数")
    return parsed


def temperature(value: str) -> float:
    parsed = float(value)
    if parsed < 0 or parsed > 2:
        raise argparse.ArgumentTypeError("必须在 0 到 2 之间")
    return parsed
