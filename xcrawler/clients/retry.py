from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import requests

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RequestAttemptResult:
    response: requests.Response
    data: dict[str, Any]
    requests_used: int
    retries: int


class RequestAttemptsError(RuntimeError):
    def __init__(self, message: str, *, requests_used: int, retries: int, stop_reason: str):
        super().__init__(message)
        self.requests_used = requests_used
        self.retries = retries
        self.stop_reason = stop_reason


def request_json_with_retries(
    url: str,
    *,
    headers: dict[str, str],
    params: dict[str, Any],
    request_get: Callable[..., requests.Response],
    max_retries: int,
    request_budget: int,
    page_number: int,
    max_rate_limit_wait: int = 60,
    sleep: Callable[[float], None] = time.sleep,
) -> RequestAttemptResult:
    requests_used = 0
    retries = 0
    for attempt in range(1, max_retries + 1):
        if requests_used >= request_budget:
            raise RequestAttemptsError(
                f"请求预算已用完（{requests_used}/{request_budget}）",
                requests_used=requests_used,
                retries=retries,
                stop_reason="request_budget",
            )
        try:
            requests_used += 1
            logger.debug(
                "HTTP attempt page=%d attempt=%d/%d budget=%d/%d url=%s",
                page_number,
                attempt,
                max_retries,
                requests_used,
                request_budget,
                url,
            )
            response = request_get(url, headers=headers, params=params, timeout=10)
            logger.debug("HTTP response page=%d status=%d", page_number, response.status_code)
            if response.status_code == 429:
                reset_time = response.headers.get("x-rate-limit-reset")
                if reset_time is None:
                    wait_seconds = min(2 ** (attempt - 1), 8)
                else:
                    try:
                        wait_seconds = max(0, int(float(reset_time)) - int(time.time()))
                    except (TypeError, ValueError) as error:
                        raise RequestAttemptsError(
                            "API 限流重置时间无效",
                            requests_used=requests_used,
                            retries=retries,
                            stop_reason="invalid_rate_limit_reset",
                        ) from error
                if wait_seconds > max_rate_limit_wait:
                    raise RequestAttemptsError(
                        f"API 限流需等待 {wait_seconds} 秒，超过最大等待时间",
                        requests_used=requests_used,
                        retries=retries,
                        stop_reason="rate_limit_wait_too_long",
                    )
                if attempt == max_retries or requests_used >= request_budget:
                    raise RequestAttemptsError(
                        f"API 限流，重试 {retries} 次后仍未恢复",
                        requests_used=requests_used,
                        retries=retries,
                        stop_reason="rate_limited",
                    )
                retries += 1
                logger.debug("rate limited page=%d wait_seconds=%d", page_number, wait_seconds)
                print(f"⏳ API 限流，{wait_seconds} 秒后重试 ({attempt}/{max_retries})...")
                sleep(wait_seconds)
                continue

            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("response root must be an object")
            return RequestAttemptResult(response, data, requests_used, retries)
        except requests.exceptions.HTTPError as error:
            status = error.response.status_code if error.response is not None else 0
            retryable = status >= 500 or status == 0
            if status in (401, 403) or not retryable or attempt == max_retries or requests_used >= request_budget:
                raise RequestAttemptsError(
                    f"第 {page_number} 页 HTTP 错误（{status or 'unknown'}）",
                    requests_used=requests_used,
                    retries=retries,
                    stop_reason="http_error",
                ) from error
        except requests.exceptions.RequestException as error:
            if attempt == max_retries or requests_used >= request_budget:
                raise RequestAttemptsError(
                    f"第 {page_number} 页网络错误",
                    requests_used=requests_used,
                    retries=retries,
                    stop_reason="network_error",
                ) from error
        except ValueError as error:
            if attempt == max_retries or requests_used >= request_budget:
                raise RequestAttemptsError(
                    f"第 {page_number} 页响应解析失败",
                    requests_used=requests_used,
                    retries=retries,
                    stop_reason="invalid_response",
                ) from error

        retries += 1
        delay = min(2 ** (attempt - 1), 8)
        logger.debug("retry scheduled page=%d delay_seconds=%d", page_number, delay)
        print(f"⚠️ 第 {page_number} 页请求失败，{delay} 秒后重试 ({attempt}/{max_retries})...")
        sleep(delay)

    raise RequestAttemptsError(
        f"第 {page_number} 页请求失败",
        requests_used=requests_used,
        retries=retries,
        stop_reason="retry_exhausted",
    )
