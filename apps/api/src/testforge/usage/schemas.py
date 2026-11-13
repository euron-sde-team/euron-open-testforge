from __future__ import annotations

from datetime import date

from testforge.core.schemas import ApiModel


class UsageCounts(ApiModel):
    generations: int = 0
    tests_accepted: int = 0
    tests_rejected: int = 0
    runs: int = 0
    runs_failed: int = 0
    sandbox_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


class UsageByDay(UsageCounts):
    day: date


class UsageByModel(UsageCounts):
    model: str


class UsageReport(ApiModel):
    days: int
    totals: UsageCounts
    by_day: list[UsageByDay]
    by_model: list[UsageByModel]
