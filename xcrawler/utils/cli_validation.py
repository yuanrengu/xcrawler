from __future__ import annotations

import argparse
import re

X_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{1,15}$")


def validate_x_username(value: str) -> str:
    username = value.strip().removeprefix("@")
    if not X_USERNAME_PATTERN.fullmatch(username):
        raise ValueError("X 用户名必须为 1-15 位字母、数字或下划线")
    return username


def x_username(value: str) -> str:
    try:
        return validate_x_username(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


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
