# Batch `build_match_catalog` DB Queries — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace 63,191 per-product DB queries in `build_match_catalog` with one query per set + one ref_id lookup, dropping wall time from ~13 min to under 30 s.

**Architecture:** Add two read methods to `CardReferenceRepository` — `get_tcgplayer_ref_id()` (called once) and `get_all_card_versions_for_set()` (called once per set, returns a `{card_name: [rows]}` dict). Refactor the service loop to use the dict instead of per-product awaits. Delete the now-unused `fetch_versions_by_set_and_name`.

**Tech Stack:** asyncpg, Python 3.12, pytest

---

## Files

| Action | Path |
|--------|------|
| Modify | `src/automana/core/repositories/card_catalog/card_repository.py` |
| Modify | `src/automana/core/services/app_integration/pricecharting/pc_match_catalog_service.py` |
| Modify | `tests/unit/core/services/pricecharting/test_pc_matching.py` (add repo method unit tests) |

---

### Task 1: Add `get_tcgplayer_ref_id` and `get_all_card_versions_for_set` to `CardReferenceRepository`

**Files:**
- Modify: `src/automana/core/repositories/card_catalog/card_repository.py:222-252`
- Test: `tests/unit/core/services/pricecharting/test_pc_matching.py`

- [ ] **Step 1: Write failing tests for the two new repo methods**

Add to `tests/unit/core/services/pricecharting/test_pc_matching.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from automana.core.repositories.card_catalog.card_repository import CardReferenceRepository


# ── get_tcgplayer_ref_id ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_tcgplayer_ref_id_returns_int():
    repo = CardReferenceRepository.__new__(CardReferenceRepository)
    row = MagicMock()
    row.__getitem__ = lambda self, k: 4  # ref_id = 4
    repo.execute_query = AsyncMock(return_value=[row])
    result = await repo.get_tcgplayer_ref_id()
    assert result == 4
    repo.execute_query.assert_called_once()
    sql = repo.execute_query.call_args[0][0]
    assert "card_identifier_ref" in sql
    assert "tcgplayer_id" in sql


@pytest.mark.asyncio
async def test_get_tcgplayer_ref_id_raises_if_not_found():
    repo = CardReferenceRepository.__new__(CardReferenceRepository)
    repo.execute_query = AsyncMock(return_value=[])
    with pytest.raises(ValueError, match="tcgplayer_id"):
        await repo.get_tcgplayer_ref_id()


# ── get_all_card_versions_for_set ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_all_card_versions_for_set_groups_by_name():
    repo = CardReferenceRepository.__new__(CardReferenceRepository)

    def make_row(card_version_id, card_name, collector_number):
        r = MagicMock()
        r.__iter__ = MagicMock(return_value=iter([
            ("card_version_id", card_version_id),
            ("card_name", card_name),
            ("collector_number", collector_number),
            ("frame_effects", []),
            ("full_art", False),
            ("border_color_name", "black"),
            ("tcgplayer_id", None),
        ]))
        # dict(row) path
        r.keys = MagicMock(return_value=["card_version_id","card_name","collector_number",
                                          "frame_effects","full_art","border_color_name","tcgplayer_id"])
        r.__getitem__ = lambda self, k: {
            "card_version_id": card_version_id, "card_name": card_name,
            "collector_number": collector_number, "frame_effects": [],
            "full_art": False, "border_color_name": "black", "tcgplayer_id": None,
        }[k]
        return r

    rows = [
        make_row("uuid-1", "Lightning Bolt", "1"),
        make_row("uuid-2", "Lightning Bolt", "250"),  # foil variant
        make_row("uuid-3", "Counterspell", "55"),
    ]
    repo.execute_query = AsyncMock(return_value=rows)

    result = await repo.get_all_card_versions_for_set("lea", 4)

    assert "lightning bolt" in result
    assert len(result["lightning bolt"]) == 2
    assert "counterspell" in result
    assert len(result["counterspell"]) == 1
    repo.execute_query.assert_called_once()
    call_args = repo.execute_query.call_args[0]
    assert call_args[1] == ("lea", 4)  # (set_code, tcgplayer_ref_id)


@pytest.mark.asyncio
async def test_get_all_card_versions_for_set_returns_empty_dict_for_unknown_set():
    repo = CardReferenceRepository.__new__(CardReferenceRepository)
    repo.execute_query = AsyncMock(return_value=[])
    result = await repo.get_all_card_versions_for_set("zzz", 4)
    assert result == {}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/arthur/projects/AutoMana
.venv/bin/pytest tests/unit/core/services/pricecharting/test_pc_matching.py \
  -k "tcgplayer_ref_id or card_versions_for_set" -v 2>&1 | tail -20
```

Expected: `AttributeError: type object 'CardReferenceRepository' has no attribute 'get_tcgplayer_ref_id'`

- [ ] **Step 3: Add the two methods to `CardReferenceRepository`**

In `src/automana/core/repositories/card_catalog/card_repository.py`, **replace** `fetch_versions_by_set_and_name` (lines 222–252) with the two new methods:

```python
    async def get_tcgplayer_ref_id(self) -> int:
        """Look up the card_identifier_ref_id for 'tcgplayer_id' (constant — call once)."""
        sql = """
            SELECT card_identifier_ref_id
            FROM   card_catalog.card_identifier_ref
            WHERE  identifier_name = 'tcgplayer_id'
        """
        rows = await self.execute_query(sql)
        if not rows:
            raise ValueError("card_identifier_ref row for 'tcgplayer_id' not found")
        return rows[0]["card_identifier_ref_id"]

    async def get_all_card_versions_for_set(
        self, set_code: str, tcgplayer_ref_id: int
    ) -> dict[str, list[dict]]:
        """All card_version rows for a set, keyed by lowercased card name.

        Returns {card_name.lower(): [row_dict, ...]} so the caller can look up
        candidates by name in O(1) without issuing a query per product.
        The tcgplayer_id column is populated via the pre-resolved ref_id to avoid
        a correlated subquery on every call.
        """
        sql = """
            SELECT cv.card_version_id,
                   cv.collector_number,
                   cv.frame_effects,
                   cv.full_art,
                   bc.border_color_name,
                   uc.card_name,
                   cei.value AS tcgplayer_id
            FROM   card_catalog.card_version cv
            JOIN   card_catalog.sets s
                   ON s.set_id = cv.set_id
            JOIN   card_catalog.unique_cards_ref uc
                   ON uc.unique_card_id = cv.unique_card_id
            JOIN   card_catalog.border_color_ref bc
                   ON bc.border_color_id = cv.border_color_id
            LEFT JOIN card_catalog.card_external_identifier cei
                   ON  cei.card_version_id        = cv.card_version_id
                   AND cei.card_identifier_ref_id = $2
            WHERE  UPPER(s.set_code) = UPPER($1)
        """
        rows = await self.execute_query(sql, (set_code, tcgplayer_ref_id))
        result: dict[str, list[dict]] = {}
        for row in rows:
            r = dict(row)
            key = r["card_name"].lower()
            result.setdefault(key, []).append(r)
        return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/unit/core/services/pricecharting/test_pc_matching.py \
  -k "tcgplayer_ref_id or card_versions_for_set" -v 2>&1 | tail -20
```

Expected: all 4 new tests PASS.

- [ ] **Step 5: Verify `fetch_versions_by_set_and_name` is deleted**

Confirm it no longer appears in `card_repository.py` (it was lines 222–252):

```bash
grep -n "fetch_versions_by_set_and_name" \
  src/automana/core/repositories/card_catalog/card_repository.py
```

Expected: no output. If grep finds a match, delete the method.

- [ ] **Step 6: Run the full test suite to check for regressions**

```bash
.venv/bin/pytest tests/unit/core/services/pricecharting/ -v 2>&1 | tail -20
```

Expected: all existing tests still PASS.

- [ ] **Step 7: Commit**

```bash
git add src/automana/core/repositories/card_catalog/card_repository.py \
        tests/unit/core/services/pricecharting/test_pc_matching.py
git commit -m "feat(pricecharting): add get_tcgplayer_ref_id + get_all_card_versions_for_set to CardReferenceRepository (#361)"
```

---

### Task 2: Refactor `build_match_catalog` to use per-set batch fetch

**Files:**
- Modify: `src/automana/core/services/app_integration/pricecharting/pc_match_catalog_service.py`

- [ ] **Step 1: Replace the service loop**

In `pc_match_catalog_service.py`, replace the body of `build_match_catalog` (lines 64–162) with:

```python
async def build_match_catalog(
    set_repository: SetReferenceRepository,
    card_repository: CardReferenceRepository,
    pricecharting_map_repository: PricechartingMapRepository,
    storage_service: StorageService,
    **kwargs: Any,
) -> dict:
    """Resolve PriceCharting products to card_versions and persist the matches.

    Requires ``pricecharting.scrape_catalog`` (sets.json + products/{uid}.json).
    Issues one DB query per set (not per product) for card_version candidates.
    """
    if not await storage_service.file_exists("sets.json"):
        logger.warning("pricecharting_match_no_sets_file")
        return {"new_matched": 0, "new_unmatched": 0, "skipped_existing": 0,
                "skipped_sets": 0, "identifiers_registered": 0}

    existing = await pricecharting_map_repository.fetch_all_map()
    db_sets = await set_repository.fetch_sets_for_matching()
    set_index = pc_matching.build_set_code_index([dict(r) for r in db_sets])
    pc_sets = (await storage_service.load_json("sets.json")).get("sets", [])

    # Resolve the tcgplayer_id ref_id once — it's constant across all sets.
    tcgplayer_ref_id = await card_repository.get_tcgplayer_ref_id()

    upserts: list[dict] = []
    new_matched = new_unmatched = skipped_existing = skipped_sets = identifiers_registered = 0

    for set_info in pc_sets:
        uid = set_info["uid"]
        set_code, set_method = pc_matching.match_set_code(set_info["name"], set_index)
        if not set_code:
            skipped_sets += 1
            continue

        catalog_key = f"products/{uid}.json"
        if not await storage_service.file_exists(catalog_key):
            skipped_sets += 1
            continue

        singles = [
            p for p in (await storage_service.load_json(catalog_key)).get("products", [])
            if p["product_type"] == "single"
        ]
        if not singles:
            continue

        tcg = await _load_tcgplayer_ids(storage_service, uid)

        # One query fetches all card_versions for the set; products look up by name.
        set_versions = await card_repository.get_all_card_versions_for_set(
            set_code, tcgplayer_ref_id
        )

        for product in singles:
            pid = product["product_id"]
            prior = existing.get(pid)
            if prior and (prior.get("card_version_id") is not None or prior.get("verified")):
                skipped_existing += 1
                continue

            card_name = pc_matching.clean_card_name(product["title"])
            candidates = set_versions.get(card_name.lower(), [])
            tcg_id, tcg_votes = tcg.get(pid, (None, 0))
            match = pc_matching.resolve_card_match(
                candidates, product["title"], tcg_id,
                set_method=set_method, tcg_votes=tcg_votes,
            )

            if not match:
                upserts.append({"pc_product_id": pid, "card_version_id": None,
                                "set_code": set_code, "finish_id": None,
                                "match_method": "none", "certainty": 0, "tcg_vote_count": tcg_votes})
                new_unmatched += 1
                continue

            upserts.append({
                "pc_product_id": pid,
                "card_version_id": match["card_version_id"],
                "set_code": set_code,
                "finish_id": match["finish_id"],
                "match_method": match["match_method"],
                "certainty": match["certainty"],
                "tcg_vote_count": tcg_votes,
            })
            new_matched += 1

            if match["certainty"] >= _REGISTER_CERTAINTY_THRESHOLD:
                try:
                    reg = await card_repository.register_external_identifier(
                        match["card_version_id"], "pricecharting_id", pid
                    )
                    if reg.inserted:
                        identifiers_registered += 1
                except Exception:
                    logger.exception(
                        "pricecharting_identifier_register_failed",
                        extra={"product_id": pid, "card_version_id": match["card_version_id"]},
                    )

    submitted = await pricecharting_map_repository.upsert_map(upserts)

    logger.info(
        "pricecharting_match_complete",
        extra={
            "new_matched": new_matched, "new_unmatched": new_unmatched,
            "skipped_existing": skipped_existing, "skipped_sets": skipped_sets,
            "identifiers_registered": identifiers_registered, "rows_upserted": submitted,
        },
    )
    return {
        "new_matched": new_matched,
        "new_unmatched": new_unmatched,
        "skipped_existing": skipped_existing,
        "skipped_sets": skipped_sets,
        "identifiers_registered": identifiers_registered,
    }
```

Note: the `candidates` list passed to `resolve_card_match` is now already a `list[dict]` from the dict lookup — the `[dict(c) for c in candidates]` wrapper is no longer needed.

- [ ] **Step 2: Run existing unit tests to confirm no regressions**

```bash
.venv/bin/pytest tests/unit/core/services/pricecharting/ -v 2>&1 | tail -20
```

Expected: all tests PASS (the service refactor touches no pure-function logic).

- [ ] **Step 3: Smoke-test on the cached 1-set catalog**

Swap in the single-set test file and run:

```bash
cp /tmp/pc_test_sets.json /data/automana_data/pricecharting/sets.json
.venv/bin/automana-run pricecharting.build_match_catalog 2>&1 | grep -E "match_complete|error|ERROR"
```

Expected log line:
```
"msg": "pricecharting_match_complete", "new_matched": 4, "new_unmatched": 1, "skipped_existing": 0
```
(5 singles in magic-unsanctioned; 1 may be unmatched depending on DB coverage.)

Restore the full catalog:
```bash
cp /data/automana_data/pricecharting/sets.json.bak /data/automana_data/pricecharting/sets.json
```

- [ ] **Step 4: Commit**

```bash
git add src/automana/core/services/app_integration/pricecharting/pc_match_catalog_service.py
git commit -m "perf(pricecharting): batch card_version queries in build_match_catalog — 63K→376 queries (#361)"
```

---

### Task 3: Verify performance on full catalog (with existing match map)

The match map already has 62,660 rows from the first run. On re-run, all previously matched products are skipped (`skipped_existing`). This still exercises the per-set batch fetch for any unmatched or newly added products.

- [ ] **Step 1: Run `build_match_catalog` on the full catalog and time it**

```bash
time .venv/bin/automana-run pricecharting.build_match_catalog \
  2>&1 | grep -E "match_complete|elapsed"
```

Expected: completes in **under 60 seconds** (most sets skipped via `skipped_existing`; the per-set batch query still runs for sets with unmatched products).

- [ ] **Step 2: Confirm row counts are stable**

```bash
docker exec automana-postgres-dev psql -U automana_admin automana \
  -c "SELECT COUNT(*) FROM pricing.pricecharting_card_map;"
```

Expected: same count as before (62,660) — the re-run skips already-resolved products and adds nothing new unless the catalog changed.

- [ ] **Step 3: Commit with issue close**

```bash
git commit --allow-empty -m "test(pricecharting): confirm build_match_catalog batching perf on full catalog

Closes #361"
```

---

### Task 4: Clean up — reset match map and do a fresh full run (optional validation)

This task is only needed if you want to validate that match *output* is identical before/after the batching change. Skip if the smoke test in Task 2 is sufficient.

- [ ] **Step 1: Clear the match map**

```bash
docker exec automana-postgres-dev psql -U automana_admin automana \
  -c "TRUNCATE pricing.pricecharting_card_map;"
```

- [ ] **Step 2: Run `build_match_catalog` fresh and record counts**

```bash
time .venv/bin/automana-run pricecharting.build_match_catalog \
  2>&1 | grep "match_complete"
```

Expected:
- Wall time: **under 30 seconds**
- `new_matched` ≈ 56,945 (same as original run)
- `new_unmatched` ≈ 5,715
- `skipped_sets` ≈ 26

Tolerable variance: ±50 rows (name normalisation edge cases are deterministic but set_code mapping may differ slightly if DB set data changed). Any large divergence (>500 rows) warrants investigation before closing.
