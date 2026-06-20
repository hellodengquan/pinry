import logging
import statistics
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

_METRICS_CACHE_KEY = "preview:metrics:summary"
_METRICS_FLUSH_INTERVAL = getattr(settings, "PREVIEW_METRICS_FLUSH_INTERVAL", 60)


@dataclass
class MetricRecord:
    operation: str
    duration_seconds: float
    content_type: Optional[str] = None
    from_cache: bool = False
    success: bool = True
    error_code: Optional[str] = None
    timestamp: float = 0.0


class MetricsCollector:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._records: Dict[str, deque] = {}
        self._max_records_per_op = 10000
        self._lock = threading.Lock()
        self._last_flush = time.time()
        self._counters: Dict[str, int] = {}
        self._start_time = time.time()

    def record(
        self,
        operation: str,
        duration_seconds: float,
        content_type: Optional[str] = None,
        from_cache: bool = False,
        success: bool = True,
        error_code: Optional[str] = None,
    ) -> None:
        record = MetricRecord(
            operation=operation,
            duration_seconds=duration_seconds,
            content_type=content_type,
            from_cache=from_cache,
            success=success,
            error_code=error_code,
            timestamp=time.time(),
        )

        with self._lock:
            if operation not in self._records:
                self._records[operation] = deque(maxlen=self._max_records_per_op)
            self._records[operation].append(record)

            counter_key = f"{operation}_total"
            self._counters[counter_key] = self._counters.get(counter_key, 0) + 1
            if from_cache:
                cache_key = f"{operation}_cache_hits"
                self._counters[cache_key] = self._counters.get(cache_key, 0) + 1
            if not success:
                error_key = f"{operation}_errors"
                self._counters[error_key] = self._counters.get(error_key, 0) + 1

    def get_operation_metrics(self, operation: str) -> Dict[str, Any]:
        with self._lock:
            records = list(self._records.get(operation, []))

        if not records:
            return {
                "operation": operation,
                "count": 0,
                "latency": None,
                "throughput_rps": 0,
                "cache_hit_rate": 0,
                "error_rate": 0,
            }

        durations = [r.duration_seconds for r in records]
        cache_hits = sum(1 for r in records if r.from_cache)
        errors = sum(1 for r in records if not r.success)

        time_span = records[-1].timestamp - records[0].timestamp
        throughput = len(records) / time_span if time_span > 0 else 0

        sorted_durations = sorted(durations)
        count = len(sorted_durations)

        latency = {
            "min": round(sorted_durations[0], 6),
            "max": round(sorted_durations[-1], 6),
            "mean": round(statistics.mean(sorted_durations), 6),
            "median": round(statistics.median(sorted_durations), 6),
        }
        if count >= 2:
            latency["p90"] = round(sorted_durations[int(count * 0.9)], 6)
            latency["p95"] = round(sorted_durations[int(count * 0.95)], 6)
            latency["p99"] = round(sorted_durations[int(count * 0.99)], 6)
            latency["stdev"] = round(statistics.stdev(sorted_durations), 6)

        error_breakdown = {}
        for r in records:
            if not r.success and r.error_code:
                error_breakdown[r.error_code] = error_breakdown.get(r.error_code, 0) + 1

        return {
            "operation": operation,
            "count": count,
            "latency": latency,
            "throughput_rps": round(throughput, 4),
            "cache_hit_rate": round(cache_hits / count, 4),
            "error_rate": round(errors / count, 4),
            "error_breakdown": error_breakdown if error_breakdown else None,
        }

    def get_all_metrics(self) -> Dict[str, Any]:
        with self._lock:
            operations = list(self._records.keys())

        per_operation = {}
        for op in operations:
            per_operation[op] = self.get_operation_metrics(op)

        uptime = time.time() - self._start_time
        total_requests = sum(
            self._counters.get(f"{op}_total", 0) for op in operations
        )
        global_throughput = total_requests / uptime if uptime > 0 else 0

        return {
            "uptime_seconds": round(uptime, 2),
            "total_operations": total_requests,
            "global_throughput_rps": round(global_throughput, 4),
            "operations": per_operation,
            "counters": dict(self._counters),
        }

    def reset(self) -> None:
        with self._lock:
            self._records.clear()
            self._counters.clear()
            self._start_time = time.time()

    def flush_to_cache(self) -> None:
        summary = self.get_all_metrics()
        try:
            cache.set(_METRICS_CACHE_KEY, summary, timeout=300)
        except Exception:
            logger.exception("Failed to flush metrics to cache")


_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector


def get_metrics_summary() -> Dict[str, Any]:
    collector = get_metrics_collector()
    return collector.get_all_metrics()


def reset_metrics() -> None:
    collector = get_metrics_collector()
    collector.reset()


def record_preview_metric(
    operation: str,
    duration_seconds: float,
    content_type: Optional[str] = None,
    from_cache: bool = False,
    success: bool = True,
    error_code: Optional[str] = None,
) -> None:
    collector = get_metrics_collector()
    collector.record(
        operation=operation,
        duration_seconds=duration_seconds,
        content_type=content_type,
        from_cache=from_cache,
        success=success,
        error_code=error_code,
    )


class PreviewMetricTimer:
    def __init__(
        self,
        operation: str,
        content_type: Optional[str] = None,
        url: Optional[str] = None,
    ):
        self.operation = operation
        self.content_type = content_type
        self.url = url
        self.start_time = 0
        self._success = True
        self._error_code = None
        self._from_cache = False

    def __enter__(self):
        self.start_time = time.monotonic()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.monotonic() - self.start_time
        if exc_type is not None:
            self._success = False
            from core.services.preview_service import PreviewError
            if isinstance(exc_val, PreviewError):
                self._error_code = exc_val.code.value

        record_preview_metric(
            operation=self.operation,
            duration_seconds=duration,
            content_type=self.content_type,
            from_cache=self._from_cache,
            success=self._success,
            error_code=self._error_code,
        )
        return False

    def set_from_cache(self, value: bool) -> None:
        self._from_cache = value

    def set_error(self, error_code: str) -> None:
        self._success = False
        self._error_code = error_code
