from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class FetchPlan:
    username: str
    pages: int
    max_results_per_page: int = 100
    endpoint: str = "users/:id/tweets"

    @property
    def estimated_requests(self) -> int:
        return max(0, self.pages)

    @property
    def estimated_max_tweets(self) -> int:
        return self.estimated_requests * self.max_results_per_page

    def to_dict(self) -> dict:
        data = asdict(self)
        data["estimated_requests"] = self.estimated_requests
        data["estimated_max_tweets"] = self.estimated_max_tweets
        return data


def build_fetch_plan(username: str, pages: int, max_results_per_page: int = 100) -> FetchPlan:
    return FetchPlan(
        username=username,
        pages=pages,
        max_results_per_page=max_results_per_page,
    )
