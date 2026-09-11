"""单篇文档LLM调用成本计数器。"""

from __future__ import annotations

import threading


class CostCounter:
    """线程安全的LLM调用计数。"""

    def __init__(self, budget: int = 20):
        self._budget = budget
        self._lock = threading.Lock()
        self._calls: list[str] = []

    def record(self, task: str) -> None:
        with self._lock:
            self._calls.append(task)

    @property
    def total(self) -> int:
        return len(self._calls)

    @property
    def remaining(self) -> int:
        return max(0, self._budget - self.total)

    def budget_exceeded(self) -> bool:
        return self.total >= self._budget

    def reset(self) -> None:
        with self._lock:
            self._calls.clear()

    def by_task(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for t in self._calls:
            result[t] = result.get(t, 0) + 1
        return result


__all__ = ["CostCounter"]