"""Metric registry — parallel to ServiceRegistry, scoped to sanity-report metrics.

Each metric is a decorated async function that queries a small, well-defined
slice of the DB and returns a `MetricResult`. The runner service picks a subset
(by name list, category, or path prefix) and wraps the outcomes in the same
report envelope used by `ops.integrity.*` services.

Severity is declarative. Prefer `Threshold(warn, error, direction)` for
numeric metrics — it's introspectable, JSON-serializable, and kept in sync
with the value's "lower is worse" or "higher is worse" semantics. Fall back
to `Callable[[Any], Severity]` only for non-numeric cases (e.g. matching a
status string).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Literal, Optional, Union

import logging

logger = logging.getLogger(__name__)


# Category is a closed set. Kept as tuple + Literal rather than StrEnum to
# avoid an import at every decorator call site (matches the `str` style used
# across the rest of the codebase).
Category = Literal["health", "volume", "timing", "status"]
_CATEGORIES: tuple[str, ...] = ("health", "volume", "timing", "status")


class Severity(str, Enum):
    OK = "ok"
    WARN = "warn"
    ERROR = "error"


Direction = Literal["lower_is_worse", "higher_is_worse"]


@dataclass(frozen=True)
class Threshold:
    """Declarative severity rule for a numeric metric.

    `direction` makes the comparison explicit instead of hiding it in a lambda
    body. `evaluate` returns ERROR when the error bound is breached, WARN when
    only the warn bound is breached, OK otherwise.
    """
    warn: float
    error: float
    direction: Direction = "higher_is_worse"

    def evaluate(self, value: float) -> Severity:
        if value is None:
            return Severity.WARN
        if self.direction == "higher_is_worse":
            if value >= self.error:
                return Severity.ERROR
            if value >= self.warn:
                return Severity.WARN
            return Severity.OK
        # lower_is_worse
        if value <= self.error:
            return Severity.ERROR
        if value <= self.warn:
            return Severity.WARN
        return Severity.OK


SeverityRule = Union[Threshold, Callable[[Any], Severity]]


@dataclass(frozen=True)
class MetricResult:
    """Contract a metric function must honor.

    `row_count` is the headline scalar rendered in the report envelope.
    `details` is a free-form JSON-serializable dict for whatever context is
    useful to the operator (per-step breakdown, raw counts behind a ratio,
    etc.).
    """
    row_count: Union[int, float, str, None]
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MetricConfig:
    path: str
    category: Category
    description: str
    severity: Optional[SeverityRule]
    db_repositories: List[str]
    module: str
    function: str


def _evaluate(rule: Optional[SeverityRule], value: Any) -> Severity:
    if rule is None:
        return Severity.OK
    if isinstance(rule, Threshold):
        return rule.evaluate(value)
    return rule(value)


class MetricRegistry:
    """Central registry for all metric functions.

    Metrics self-register at import time via `@MetricRegistry.register(...)`.
    Consumers import the module (directly, or transitively via
    `SERVICE_MODULES` at startup) and then call `select()` to pick a subset.
    """
    _metrics: Dict[str, MetricConfig] = {}

    @classmethod
    def register(
        cls,
        path: str,
        *,
        category: Category,
        description: str,
        severity: Optional[SeverityRule] = None,
        db_repositories: Optional[List[str]] = None,
    ) -> Callable:
        if category not in _CATEGORIES:
            raise ValueError(
                f"Unknown metric category {category!r}; expected one of {_CATEGORIES}"
            )

        def decorator(func: Callable) -> Callable:
            if path in cls._metrics:
                logger.warning("metric_path_redefined", extra={"path": path})
            cls._metrics[path] = MetricConfig(
                path=path,
                category=category,
                description=description,
                severity=severity,
                db_repositories=db_repositories or [],
                module=func.__module__,
                function=func.__name__,
            )
            logger.debug("metric_registered", extra={"path": path, "category": category})
            return func

        return decorator

    @classmethod
    def get(cls, path: str) -> Optional[MetricConfig]:
        return cls._metrics.get(path)

    @classmethod
    def all_metrics(cls) -> Dict[str, MetricConfig]:
        return dict(cls._metrics)

    @classmethod
    def select(
        cls,
        names: Optional[List[str]] = None,
        category: Optional[str] = None,
        prefix: Optional[str] = None,
    ) -> List[MetricConfig]:
        """Filter metrics. All active filters must match. Result is sorted by
        path so callers and tests see deterministic iteration order."""
        if category is not None and category not in _CATEGORIES:
            raise ValueError(
                f"Unknown metric category {category!r}; expected one of {_CATEGORIES}"
            )

        selected: List[MetricConfig] = []
        for path, cfg in cls._metrics.items():
            if names is not None and path not in names:
                continue
            if category is not None and cfg.category != category:
                continue
            if prefix is not None and not path.startswith(prefix):
                continue
            selected.append(cfg)

        return sorted(selected, key=lambda c: c.path)

    @classmethod
    def evaluate(cls, config: MetricConfig, value: Any) -> Severity:
        """Apply the declared severity rule to a metric's scalar value."""
        return _evaluate(config.severity, value)

    @classmethod
    def clear(cls) -> None:
        """Test-only: wipe the registry. Do not call from production code."""
        cls._metrics.clear()