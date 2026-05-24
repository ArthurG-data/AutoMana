"""JSON staging helpers for eBay raw API responses (sweep + watchlist replay buffer)."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from automana.core.config.settings import get_settings

logger = logging.getLogger(__name__)

_SWEEP_SUBDIR = "sweep"
_WATCHLIST_SUBDIR = "watchlist"


def get_ebay_raw_dir() -> Path:
    settings = get_settings()
    return Path(getattr(settings, "data_dir", "/data")) / "ebay_raw"


def sweep_path(today: str, marketplace: str) -> Path:
    return get_ebay_raw_dir() / today / _SWEEP_SUBDIR / f"{marketplace}.json"


def watchlist_path(today: str, source_product_id: int, marketplace: str) -> Path:
    return get_ebay_raw_dir() / today / _WATCHLIST_SUBDIR / f"{source_product_id}_{marketplace}.json"


def load_items_from_json(path: Path) -> list[dict]:
    """Load items list from a staged JSON file. Raises ValueError if corrupt or missing 'items' key."""
    try:
        data = json.loads(path.read_text())
        return data["items"]
    except (json.JSONDecodeError, KeyError, OSError) as exc:
        raise ValueError(f"Corrupt or unreadable replay file: {path}") from exc


def write_items_to_json(
    path: Path,
    items: list[dict],
    marketplace: str,
    source_product_id: Optional[int] = None,
) -> None:
    """Write API items to a staged JSON file. Creates parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "marketplace": marketplace,
        "source_product_id": source_product_id,
        "items": items,
    }
    path.write_text(json.dumps(payload, default=str))
