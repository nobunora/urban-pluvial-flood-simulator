"""Stable API error envelope for application-owned route failures."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ApiContractError(Exception):
    status_code: int
    code: str
    message: str
    retryable: bool = False
    stage: str | None = None
