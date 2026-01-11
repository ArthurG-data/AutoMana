from dataclasses import dataclass
from typing import Optional
import json

@dataclass
class MTGStockBatchStep:
    ingestion_run_id: int
    batch_seq: int
    range_start: int
    range_end: int
    status: str
    items_ok: int
    items_failed: int
    bytes_processed: int
    duration_ms: Optional[float] = None
    error_code: Optional[str] = None
    error_details: Optional[dict] = None

    def to_dict(self):
        return {
            "ingestion_run_id": self.ingestion_run_id,
            "batch_seq": self.batch_seq,
            "range_start": self.range_start,
            "range_end": self.range_end,
            "status": self.status,
            "items_ok": self.items_ok,
            "items_failed": self.items_failed,
            "bytes_processed": self.bytes_processed,
            "duration_ms": self.duration_ms,
            "error_code": self.error_code,
            "error_details": self.error_details,
        }
    def to_tuple(self):
        return (
            self.ingestion_run_id,
            self.batch_seq,
            self.range_start,
            self.range_end,
            self.status,
            self.items_ok,
            self.items_failed,
            self.bytes_processed,
            self.duration_ms,
            self.error_code,
            json.dumps(self.error_details) if self.error_details is not None else None
        )