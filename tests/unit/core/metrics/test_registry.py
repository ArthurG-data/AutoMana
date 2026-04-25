"""
Tests for src/automana/core/metrics/registry.py

Units under test:
    - Severity enum
    - Threshold.evaluate (both directions, None input, boundary values)
    - MetricResult dataclass defaults
    - MetricRegistry.register (category validation, decorator wraps function)
    - MetricRegistry.get / all_metrics
    - MetricRegistry.select (name filter, category filter, prefix filter,
                             combined filters, sorted output, unknown category)
    - MetricRegistry.evaluate (with Threshold, with callable, with None)

Isolation: every test in this module uses the ``isolated_registry`` fixture
so registrations from the mtgstock package (loaded at import time) do not
pollute the assertions.
"""
import pytest
from automana.core.metrics.registry import (
    MetricRegistry,
    MetricResult,
    Severity,
    Threshold,
    _evaluate,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Severity enum
# ---------------------------------------------------------------------------

class TestSeverity:
    def test_values_are_lowercase_strings(self):
        assert Severity.OK.value == "ok"
        assert Severity.WARN.value == "warn"
        assert Severity.ERROR.value == "error"

    def test_is_string_subclass(self):
        # Severity is `str, Enum` — usable directly as a string key
        assert isinstance(Severity.OK, str)


# ---------------------------------------------------------------------------
# Threshold.evaluate — higher_is_worse direction
# ---------------------------------------------------------------------------

class TestThresholdHigherIsWorse:
    def setup_method(self):
        self.t = Threshold(warn=10, error=20, direction="higher_is_worse")

    def test_below_warn_is_ok(self):
        assert self.t.evaluate(5) == Severity.OK

    def test_at_warn_boundary_is_warn(self):
        assert self.t.evaluate(10) == Severity.WARN

    def test_between_warn_and_error_is_warn(self):
        assert self.t.evaluate(15) == Severity.WARN

    def test_at_error_boundary_is_error(self):
        assert self.t.evaluate(20) == Severity.ERROR

    def test_above_error_is_error(self):
        assert self.t.evaluate(999) == Severity.ERROR

    def test_none_value_is_warn(self):
        assert self.t.evaluate(None) == Severity.WARN


# ---------------------------------------------------------------------------
# Threshold.evaluate — lower_is_worse direction
# ---------------------------------------------------------------------------

class TestThresholdLowerIsWorse:
    def setup_method(self):
        self.t = Threshold(warn=50, error=10, direction="lower_is_worse")

    def test_above_warn_is_ok(self):
        assert self.t.evaluate(100) == Severity.OK

    def test_at_warn_boundary_is_warn(self):
        assert self.t.evaluate(50) == Severity.WARN

    def test_between_error_and_warn_is_warn(self):
        assert self.t.evaluate(30) == Severity.WARN

    def test_at_error_boundary_is_error(self):
        assert self.t.evaluate(10) == Severity.ERROR

    def test_below_error_is_error(self):
        assert self.t.evaluate(0) == Severity.ERROR

    def test_none_value_is_warn(self):
        assert self.t.evaluate(None) == Severity.WARN


# ---------------------------------------------------------------------------
# MetricResult defaults
# ---------------------------------------------------------------------------

class TestMetricResult:
    def test_details_defaults_to_empty_dict(self):
        result = MetricResult(row_count=42)
        assert result.details == {}

    def test_details_instances_are_independent(self):
        r1 = MetricResult(row_count=1)
        r2 = MetricResult(row_count=2)
        # Each instance gets its own default dict (field(default_factory=dict))
        assert r1.details is not r2.details


# ---------------------------------------------------------------------------
# MetricRegistry.register — category validation
# ---------------------------------------------------------------------------

class TestMetricRegistryRegister:
    def test_unknown_category_raises_at_decoration_time(self, isolated_registry):
        with pytest.raises(ValueError, match="Unknown metric category"):
            @MetricRegistry.register(
                path="test.bad_category",
                category="nonsense",
                description="should fail",
            )
            async def _dummy():
                pass

    def test_register_stores_config_and_returns_original_function(self, isolated_registry):
        async def my_metric():
            pass

        decorated = MetricRegistry.register(
            path="test.my_metric",
            category="health",
            description="a test metric",
        )(my_metric)

        # The decorator must return the original function unchanged
        assert decorated is my_metric
        cfg = MetricRegistry.get("test.my_metric")
        assert cfg is not None
        assert cfg.path == "test.my_metric"
        assert cfg.category == "health"
        assert cfg.description == "a test metric"
        assert cfg.severity is None
        assert cfg.db_repositories == []

    def test_register_stores_severity_and_repositories(self, isolated_registry):
        threshold = Threshold(warn=5, error=10)

        async def typed_metric():
            pass

        MetricRegistry.register(
            path="test.typed",
            category="volume",
            description="typed metric",
            severity=threshold,
            db_repositories=["ops", "price"],
        )(typed_metric)

        cfg = MetricRegistry.get("test.typed")
        assert cfg.severity is threshold
        assert cfg.db_repositories == ["ops", "price"]

    def test_all_valid_categories_are_accepted(self, isolated_registry):
        for i, cat in enumerate(("health", "volume", "timing", "status")):
            async def _f():
                pass
            MetricRegistry.register(
                path=f"test.cat_{i}",
                category=cat,
                description=f"cat {cat}",
            )(_f)
        assert len(MetricRegistry.all_metrics()) == 4


# ---------------------------------------------------------------------------
# MetricRegistry.get and all_metrics
# ---------------------------------------------------------------------------

class TestMetricRegistryGet:
    def test_get_returns_none_for_missing_path(self, isolated_registry):
        assert MetricRegistry.get("does.not.exist") is None

    def test_all_metrics_returns_a_copy_not_the_live_dict(self, isolated_registry):
        async def _m():
            pass
        MetricRegistry.register(path="test.m", category="health", description="x")(_m)

        snapshot = MetricRegistry.all_metrics()
        snapshot["injected"] = object()

        # The registry itself was not modified
        assert "injected" not in MetricRegistry._metrics


# ---------------------------------------------------------------------------
# MetricRegistry.select — filters and sort order
# ---------------------------------------------------------------------------

class TestMetricRegistrySelect:
    def _populate(self, isolated_registry):
        """Register three metrics in deliberately non-alphabetical order."""
        for path, cat in [
            ("test.z_metric", "health"),
            ("test.a_metric", "volume"),
            ("test.m_metric", "timing"),
        ]:
            async def _f():
                pass
            _f.__name__ = path.split(".")[-1]
            MetricRegistry.register(path=path, category=cat, description=path)(_f)

    def test_no_filters_returns_all_sorted_by_path(self, isolated_registry):
        self._populate(isolated_registry)
        results = MetricRegistry.select()
        paths = [c.path for c in results]
        assert paths == sorted(paths)
        assert paths == ["test.a_metric", "test.m_metric", "test.z_metric"]

    def test_names_filter_excludes_non_matching(self, isolated_registry):
        self._populate(isolated_registry)
        results = MetricRegistry.select(names=["test.a_metric", "test.z_metric"])
        paths = {c.path for c in results}
        assert paths == {"test.a_metric", "test.z_metric"}

    def test_category_filter_keeps_only_matching_category(self, isolated_registry):
        self._populate(isolated_registry)
        results = MetricRegistry.select(category="volume")
        assert len(results) == 1
        assert results[0].path == "test.a_metric"

    def test_prefix_filter_keeps_only_matching_prefix(self, isolated_registry):
        self._populate(isolated_registry)
        # Register a metric with a different prefix
        async def _other():
            pass
        MetricRegistry.register(path="other.metric", category="health", description="other")(_other)

        results = MetricRegistry.select(prefix="test.")
        assert all(c.path.startswith("test.") for c in results)
        assert len(results) == 3

    def test_combined_names_and_category_filter(self, isolated_registry):
        self._populate(isolated_registry)
        # names includes test.a_metric (volume) and test.z_metric (health)
        # category=volume → only test.a_metric should pass both filters
        results = MetricRegistry.select(
            names=["test.a_metric", "test.z_metric"],
            category="volume",
        )
        assert len(results) == 1
        assert results[0].path == "test.a_metric"

    def test_unknown_category_in_select_raises_value_error(self, isolated_registry):
        with pytest.raises(ValueError, match="Unknown metric category"):
            MetricRegistry.select(category="garbage")

    def test_names_not_in_registry_returns_empty(self, isolated_registry):
        results = MetricRegistry.select(names=["not.registered"])
        assert results == []


# ---------------------------------------------------------------------------
# MetricRegistry.evaluate and _evaluate
# ---------------------------------------------------------------------------

class TestMetricRegistryEvaluate:
    def _make_config(self, severity):
        """Build a minimal MetricConfig for evaluate tests."""
        from automana.core.metrics.registry import MetricConfig
        return MetricConfig(
            path="test.eval",
            category="health",
            description="eval test",
            severity=severity,
            db_repositories=[],
            module=__name__,
            function="_dummy",
        )

    def test_none_severity_rule_always_returns_ok(self):
        cfg = self._make_config(severity=None)
        assert MetricRegistry.evaluate(cfg, 9999) == Severity.OK
        assert MetricRegistry.evaluate(cfg, None) == Severity.OK

    def test_threshold_severity_delegates_to_threshold_evaluate(self):
        t = Threshold(warn=10, error=20, direction="higher_is_worse")
        cfg = self._make_config(severity=t)
        assert MetricRegistry.evaluate(cfg, 5) == Severity.OK
        assert MetricRegistry.evaluate(cfg, 15) == Severity.WARN
        assert MetricRegistry.evaluate(cfg, 25) == Severity.ERROR

    def test_callable_severity_is_invoked_with_value(self):
        called_with = []

        def my_rule(value):
            called_with.append(value)
            return Severity.WARN

        cfg = self._make_config(severity=my_rule)
        result = MetricRegistry.evaluate(cfg, "some_status")
        assert result == Severity.WARN
        assert called_with == ["some_status"]
