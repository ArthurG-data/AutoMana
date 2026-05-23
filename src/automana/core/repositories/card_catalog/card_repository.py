import io
import json
import logging
from datetime import date
from typing import Optional, Any, Dict, List
from uuid import UUID
from dataclasses import dataclass, field

import orjson

from automana.core.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository
from automana.core.repositories.card_catalog import card_queries as queries
from automana.core.utils.redis_cache import get_redis_client

logger = logging.getLogger(__name__)

_PRICE_SPARK_TTL = 86400  # 24 h — prices update once per day

class CardReferenceRepository(AbstractRepository[Any]):
    def __init__(self, connection, executor = None):
        super().__init__(connection, executor)

    @property
    def name(self) -> str:
        return "CardRepository"
    
    async def add(self, value : tuple) -> UUID|None:
       row = await self.execute_command(queries.insert_full_card_query, value)
       return row

    @dataclass(slots=True)
    class BatchInsertResponse:
        total_processed: int
        successful_inserts: int
        failed_inserts: int
        success_rate: float = field(init=False)
        inserted_card_ids: list[UUID]
        errors: list[str]

        def __post_init__(self)->None:
            self.success_rate = (
                self.successful_inserts / self.total_processed * 100
                if self.total_processed > 0
                else 0
            )

    async def _copy_csv_to_table(self, buffer :bytes, schema_name, table_name):
        data = buffer.getvalue()  # convert BytesIO -> bytes
        data_mv = memoryview(data)
        assert isinstance(data, (bytes, bytearray)), type(data_mv)
        status = await self.execute_copy_to_table(
            table_name,
            data_mv,
            schema_name=schema_name,
            format='csv',
            null='',
            delimiter='\t',
            header=False,
        )
        return status

        
    async def add_many(self, values):
        #not async anymore
        result = await self.execute_query("SELECT * FROM card_catalog.insert_batch_card_versions($1::JSONB)", (values,))
        batch_result = result[0] if result else {}

        def _parse_jsonb(val, default):
            # asyncpg returns jsonb columns as raw JSON strings — parse to Python object
            if isinstance(val, str):
                import json
                return json.loads(val)
            return val if val is not None else default

        response = CardReferenceRepository.BatchInsertResponse(
            total_processed=batch_result.get('total_processed', 0),
            successful_inserts=batch_result.get('successful_inserts', 0),
            failed_inserts=batch_result.get('failed_inserts', 0),
            inserted_card_ids=_parse_jsonb(batch_result.get('inserted_card_ids'), []),
            errors=_parse_jsonb(batch_result.get('error_details'), [])
        )
        return response

    async def delete(self, card_id: UUID):
        rows = await self.execute_query(queries.delete_card_query, (card_id,))
        return len(rows) > 0

    async def update(self, item):
        pass

    async def get(self,
                  card_id: UUID,
                 ) -> dict[str, Any]|None:
        query = """
            SELECT
                v.card_version_id,
                v.unique_card_id,
                v.card_name,
                v.rarity_name,
                v.set_name,
                v.set_code,
                v.cmc,
                v.oracle_text,
                v.mana_cost,
                v.type_line,
                v.collector_number,
                v.promo_types,
                v.legalities,
                v.is_multifaced,
                v.is_digital          AS digital,
                v.illustrations->0->>'artist_name'              AS artist,
                v.illustrations->0->'image_uris'->>'large'      AS image_large,
                ARRAY(
                    SELECT LOWER(cf.code)
                    FROM card_catalog.card_version_finish cvf
                    JOIN card_catalog.card_finished cf ON cf.finish_id = cvf.finish_id
                    WHERE cvf.card_version_id = v.card_version_id
                ) AS available_finishes,
                cv.card_back_id,
                COALESCE(
                    (
                        SELECT i.image_uris->>'large'
                        FROM   card_catalog.card_faces face
                        JOIN   card_catalog.face_illustration fi
                                   ON fi.face_id = face.card_faces_id
                        JOIN   card_catalog.illustrations i
                                   ON i.illustration_id = fi.illustration_id
                        WHERE  face.card_version_id = v.card_version_id
                          AND  face.face_index = 1
                        LIMIT  1
                    ),
                    CASE
                        WHEN v.is_multifaced = TRUE
                         AND v.illustrations->0->'image_uris'->>'large' LIKE '%/front/%'
                        THEN replace(
                            v.illustrations->0->'image_uris'->>'large',
                            '/front/', '/back/'
                        )
                    END
                ) AS back_face_image_uri
            FROM card_catalog.v_card_versions_complete v
            JOIN card_catalog.card_version cv ON cv.card_version_id = v.card_version_id
            WHERE v.card_version_id = $1;
        """
        result = await self.execute_query(query, (card_id,))
        if not result:
            return None
        row = dict(result[0])
        if isinstance(row.get("legalities"), str):
            row["legalities"] = json.loads(row["legalities"])
        price_data = await self._fetch_prices_for_cards([card_id])
        row.update(price_data.get(str(card_id), self._PRICE_DEFAULTS))
        return row

    async def get_scrape_metadata(self, card_version_id: UUID) -> dict | None:
        """Return frame/promo attributes needed by the global market scraper."""
        query = """
            SELECT
                v.card_name,
                v.set_code,
                v.frame_effects,
                v.is_promo,
                v.promo_types,
                v.border_color_name,
                v.full_art
            FROM card_catalog.v_card_versions_complete v
            WHERE v.card_version_id = $1;
        """
        result = await self.execute_query(query, (card_version_id,))
        if not result:
            return None
        return dict(result[0])

    async def suggest(self, query: str, limit: int = 10) -> list[dict]:
        sql = """
            SELECT v.card_version_id, v.card_name, v.set_code, v.rarity_name,
                   cv.collector_number,
                   cei.value AS scryfall_id,
                   word_similarity($1, v.card_name) AS score
            FROM card_catalog.v_card_name_suggest v
            JOIN card_catalog.card_version cv ON cv.card_version_id = v.card_version_id
            LEFT JOIN card_catalog.card_external_identifier cei
                ON cei.card_version_id = v.card_version_id AND cei.card_identifier_ref_id = 1
            WHERE $1 % v.card_name
              AND cv.is_digital = false
            ORDER BY score DESC
            LIMIT $2
        """
        rows = await self.execute_query(sql, (query, limit))
        return [dict(r) for r in rows]

    async def get_purchase_uris(self, card_version_id) -> dict | None:
        sql = "SELECT purchase_uris FROM card_catalog.card_version WHERE card_version_id = $1"
        rows = await self.execute_query(sql, (card_version_id,))
        if not rows:
            return None
        return rows[0]["purchase_uris"]

    async def get_version_by_scryfall_id(self, scryfall_id: str) -> Optional[dict]:
        sql = """
            SELECT cv.card_version_id, uc.card_name, s.set_code, cv.collector_number
            FROM card_catalog.card_external_identifier cei
            JOIN card_catalog.card_version cv ON cv.card_version_id = cei.card_version_id
            JOIN card_catalog.unique_cards_ref uc ON uc.unique_card_id = cv.unique_card_id
            JOIN card_catalog.sets s ON s.set_id = cv.set_id
            WHERE cei.card_identifier_ref_id = 1 AND cei.value = $1
        """
        rows = await self.execute_query(sql, (scryfall_id,))
        return dict(rows[0]) if rows else None

    async def get_version_by_set_collector(self, set_code: str, collector_number: str) -> Optional[dict]:
        sql = """
            SELECT cv.card_version_id, uc.card_name, s.set_code, cv.collector_number
            FROM card_catalog.card_version cv
            JOIN card_catalog.sets s ON s.set_id = cv.set_id
            JOIN card_catalog.unique_cards_ref uc ON uc.unique_card_id = cv.unique_card_id
            WHERE s.set_code = $1 AND cv.collector_number = $2
        """
        rows = await self.execute_query(sql, (set_code, collector_number))
        return dict(rows[0]) if rows else None

    async def _fetch_prices_for_cards(self, card_ids: list) -> dict:
        """
        Fetch price analytics from tier 2 (print_price_daily) for a batch of cards.

        Results are cached in Redis per card for 24 h (prices update once per day).
        A single mget fetches all cached entries in one roundtrip; only cache-miss
        IDs hit the database. Fresh results are written back via a Redis pipeline.

        Tier 3 (print_price_latest / print_price_weekly) covers the ALL-time chart
        via the existing get_price_history() — not touched here.
        """
        if not card_ids:
            return {}

        str_ids = [str(cid) for cid in card_ids]
        cache_keys = [f"card_price_spark:{cid}" for cid in str_ids]

        result: dict[str, dict] = {}
        miss_ids: list[str] = []

        # --- Redis: single mget roundtrip ---
        try:
            redis = await get_redis_client()
            cached_values = await redis.mget(*cache_keys)
            for cid, raw in zip(str_ids, cached_values):
                if raw is not None:
                    result[cid] = orjson.loads(raw)
                else:
                    miss_ids.append(cid)
        except Exception as exc:
            logger.warning("price_cache_read_error", extra={"error": str(exc)})
            miss_ids = str_ids  # Redis unavailable — fall through to DB

        if not miss_ids:
            return result

        # --- DB query for cache misses only ---
        sql = """
            SELECT
                card_version_id,
                price,
                price_change_1d,
                price_change_7d,
                price_change_30d,
                spark
            FROM pricing.mv_card_price_spark
            WHERE card_version_id = ANY($1::uuid[])
        """
        rows = await self.execute_query(sql, (miss_ids,))

        fresh: dict[str, dict] = {}
        for row in rows:
            cid = str(row["card_version_id"])
            fresh[cid] = {
                "price": float(row["price"]) if row["price"] is not None else None,
                "price_change_1d": float(row["price_change_1d"]) if row["price_change_1d"] is not None else 0.0,
                "price_change_7d": float(row["price_change_7d"]) if row["price_change_7d"] is not None else 0.0,
                "price_change_30d": float(row["price_change_30d"]) if row["price_change_30d"] is not None else 0.0,
                "spark": [float(v) for v in row["spark"]] if row["spark"] else [],
                "finish": "non-foil",
            }

        # --- Redis: write-back via pipeline (1 roundtrip) ---
        if fresh:
            try:
                redis = await get_redis_client()
                pipe = redis.pipeline()
                for cid, data in fresh.items():
                    pipe.setex(f"card_price_spark:{cid}", _PRICE_SPARK_TTL, orjson.dumps(data))
                await pipe.execute()
            except Exception as exc:
                logger.warning("price_cache_write_error", extra={"error": str(exc)})

        result.update(fresh)
        return result

    _PRICE_DEFAULTS = {
        "price": None,
        "price_change_1d": 0.0,
        "price_change_7d": 0.0,
        "price_change_30d": 0.0,
        "spark": [],
        "finish": "non-foil",
    }

    async def search(
            self,
            name: Optional[str] = None,
            colors: Optional[list[str]] = None,
            rarity: Optional[str] = None,
            set_name: Optional[str] = None,
            set_code: Optional[str] = None,
            mana_cost: Optional[int] = None,
            digital: Optional[bool] = None,
            card_type: Optional[str] = None,
            finish: Optional[str] = None,
            frame_effects: Optional[list[str]] = None,
            released_after: Optional[str] = None,
            released_before: Optional[str] = None,
            oracle_text: Optional[str] = None,
            artist: Optional[str] = None,
            unique_card_id: Optional[UUID] = None,
            format: Optional[str] = None,
            layout: Optional[str] = None,
            promo_type: Optional[List[str]] = None,
            collapse: bool = False,
            limit: int = 100,
            offset: int = 0,
            sort_by: Optional[str] = "card_name",
            sort_order: Optional[str] = "asc",
    ) -> dict[str, Any]:
        """Search card versions using the v_card_versions_complete materialized view.

        Filters are ANDed together. When ``name`` or ``oracle_text`` are provided
        the result is ranked by relevance; otherwise the ``sort_by`` / ``sort_order``
        pair controls ordering.

        Notes:
            - ``colors`` matches against ``color_identity`` (text[]) stored as
              proper-cased colour names (e.g. 'White', 'Blue'). Each entry adds
              an AND condition — cards must contain ALL listed colours. Callers
              must pass values in that casing.
            - ``card_type`` matches against the ``types`` array (e.g. 'Creature').
            - ``digital`` uses the per-card-version ``is_digital`` flag, not the
              legacy per-set ``sets.digital`` column.
            - ``released_after`` / ``released_before`` are satisfied via a JOIN to
              ``card_catalog.sets`` because ``v_card_versions_complete`` does not
              project ``released_at``.
        """
        conditions: list[str] = []
        values: list[Any] = []
        counter = 1
        # Parallel list for rarity facet query — receives every condition except rarity.
        # Rarity sits mid-list so we can't use a simple snapshot; we maintain a separate list.
        rf_conditions: list[str] = []
        rf_values: list[Any] = []
        rf_counter = 1

        # Track placeholder indices for relevance ORDER BY reuse —
        # the same $N bound in WHERE is referenced again in ORDER BY without
        # appending a duplicate value.
        name_param_idx: Optional[int] = None
        oracle_param_idx: Optional[int] = None

        if name:
            conditions.append(f"word_similarity(LOWER(${counter}), LOWER(v.card_name)) > 0.6")
            rf_conditions.append(f"word_similarity(LOWER(${rf_counter}), LOWER(v.card_name)) > 0.6")
            values.append(name)
            rf_values.append(name)
            name_param_idx = counter
            counter += 1
            rf_counter += 1

        for c in (colors or []):
            # color_identity is text[]; caller must use canonical casing (e.g. 'White').
            if c == 'Multi':
                # Special value: cards with 2 or more colors in their identity.
                conditions.append("array_length(v.color_identity, 1) > 1")
                rf_conditions.append("array_length(v.color_identity, 1) > 1")
                # No bind parameter added — do NOT increment counter/rf_counter.
            else:
                conditions.append(f"${counter} = ANY(v.color_identity)")
                rf_conditions.append(f"${rf_counter} = ANY(v.color_identity)")
                values.append(c)
                rf_values.append(c)
                counter += 1
                rf_counter += 1

        if rarity:
            conditions.append(f"v.rarity_name ILIKE ${counter}")
            values.append(f"%{rarity}%")
            counter += 1
            # rf_ lists intentionally not updated — rarity excluded from facet query

        if set_name:
            conditions.append(f"v.set_name ILIKE ${counter}")
            rf_conditions.append(f"v.set_name ILIKE ${rf_counter}")
            values.append(f"%{set_name}%")
            rf_values.append(f"%{set_name}%")
            counter += 1
            rf_counter += 1

        if set_code:
            conditions.append(f"v.set_code = ${counter}")
            rf_conditions.append(f"v.set_code = ${rf_counter}")
            values.append(set_code)
            rf_values.append(set_code)
            counter += 1
            rf_counter += 1

        if unique_card_id:
            # Identity filter: all printings of the same logical card share unique_card_id.
            conditions.append(f"v.unique_card_id = ${counter}")
            rf_conditions.append(f"v.unique_card_id = ${rf_counter}")
            values.append(unique_card_id)
            rf_values.append(unique_card_id)
            counter += 1
            rf_counter += 1

        if mana_cost is not None:
            conditions.append(f"v.cmc = ${counter}")
            rf_conditions.append(f"v.cmc = ${rf_counter}")
            values.append(mana_cost)
            rf_values.append(mana_cost)
            counter += 1
            rf_counter += 1

        if digital is not None:
            # v.is_digital is the per-card-version flag (differs from the old s.digital set-level flag).
            conditions.append(f"v.is_digital = ${counter}")
            rf_conditions.append(f"v.is_digital = ${rf_counter}")
            values.append(digital)
            rf_values.append(digital)
            counter += 1
            rf_counter += 1

        if released_after:
            conditions.append(f"s.released_at > ${counter}")
            rf_conditions.append(f"s.released_at > ${rf_counter}")
            values.append(released_after)
            rf_values.append(released_after)
            counter += 1
            rf_counter += 1

        if released_before:
            conditions.append(f"s.released_at < ${counter}")
            rf_conditions.append(f"s.released_at < ${rf_counter}")
            values.append(released_before)
            rf_values.append(released_before)
            counter += 1
            rf_counter += 1

        if card_type:
            # types is text[]; caller must use canonical casing (e.g. 'Creature').
            conditions.append(f"${counter} = ANY(v.types)")
            rf_conditions.append(f"${rf_counter} = ANY(v.types)")
            values.append(card_type)
            rf_values.append(card_type)
            counter += 1
            rf_counter += 1

        if finish:
            conditions.append(
                f"EXISTS (SELECT 1 FROM card_catalog.card_version_finish cvf "
                f"JOIN card_catalog.card_finished cf ON cvf.finish_id = cf.finish_id "
                f"WHERE cvf.card_version_id = v.card_version_id "
                f"AND UPPER(cf.code) = ${counter})"
            )
            rf_conditions.append(
                f"EXISTS (SELECT 1 FROM card_catalog.card_version_finish cvf "
                f"JOIN card_catalog.card_finished cf ON cvf.finish_id = cf.finish_id "
                f"WHERE cvf.card_version_id = v.card_version_id "
                f"AND UPPER(cf.code) = ${rf_counter})"
            )
            values.append(finish.upper())
            rf_values.append(finish.upper())
            counter += 1
            rf_counter += 1

        for fe in (frame_effects or []):
            conditions.append(f"${counter} = ANY(v.frame_effects)")
            rf_conditions.append(f"${rf_counter} = ANY(v.frame_effects)")
            values.append(fe)
            rf_values.append(fe)
            counter += 1
            rf_counter += 1

        if oracle_text:
            conditions.append(f"v.search_vector @@ websearch_to_tsquery('english', ${counter})")
            rf_conditions.append(f"v.search_vector @@ websearch_to_tsquery('english', ${rf_counter})")
            values.append(oracle_text)
            rf_values.append(oracle_text)
            oracle_param_idx = counter
            counter += 1
            rf_counter += 1

        if artist:
            # Match any illustration on the card whose artist_name equals the input.
            # Most cards have a single illustration; DFCs and split cards have multiple.
            conditions.append(
                f"EXISTS (SELECT 1 FROM jsonb_array_elements(v.illustrations) elem "
                f"WHERE elem->>'artist_name' = ${counter})"
            )
            rf_conditions.append(
                f"EXISTS (SELECT 1 FROM jsonb_array_elements(v.illustrations) elem "
                f"WHERE elem->>'artist_name' = ${rf_counter})"
            )
            values.append(artist)
            rf_values.append(artist)
            counter += 1
            rf_counter += 1

        if format:
            conditions.append(f"v.legalities->>${counter} = 'legal'")
            rf_conditions.append(f"v.legalities->>${rf_counter} = 'legal'")
            values.append(format)
            rf_values.append(format)
            counter += 1
            rf_counter += 1

        if layout:
            conditions.append(f"v.layout_name = ${counter}")
            rf_conditions.append(f"v.layout_name = ${rf_counter}")
            values.append(layout)
            rf_values.append(layout)
            counter += 1
            rf_counter += 1
        else:
            # Default: exclude tokens when no layout filter is specified
            conditions.append("v.layout_name NOT IN ('token', 'double_faced_token')")
            rf_conditions.append("v.layout_name NOT IN ('token', 'double_faced_token')")

        # Snapshot before adding the promo_type predicate so the promo facet query
        # can omit it — facets must show all available types across the current
        # base filter, not just types that co-occur with the selected ones.
        facet_cond_stop = len(conditions)
        facet_val_stop = len(values)

        if promo_type:
            # && = array overlap: card has ANY of the selected promo types
            conditions.append(f"v.promo_types && ${counter}")
            rf_conditions.append(f"v.promo_types && ${rf_counter}")
            values.append(promo_type)
            rf_values.append(promo_type)
            counter += 1
            rf_counter += 1

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        facet_where_clause = (
            "WHERE " + " AND ".join(conditions[:facet_cond_stop])
            if facet_cond_stop else ""
        )
        rarity_facet_where = "WHERE " + " AND ".join(rf_conditions) if rf_conditions else ""

        # Dynamic ORDER BY: prefer relevance when text search params are present.
        # collapse_order_clause mirrors order_clause but uses bare column names (no v./s.
        # prefix) so it can be applied to the outer SELECT of the DISTINCT ON subquery.
        if name_param_idx and oracle_param_idx:
            order_clause = (
                f"ORDER BY ("
                f"word_similarity(LOWER(${name_param_idx}), LOWER(v.card_name)) + "
                f"ts_rank_cd(v.search_vector, websearch_to_tsquery('english', ${oracle_param_idx}))"
                f") DESC"
            )
            collapse_order_clause = (
                f"ORDER BY ("
                f"word_similarity(LOWER(${name_param_idx}), LOWER(card_name)) + "
                f"ts_rank_cd(search_vector, websearch_to_tsquery('english', ${oracle_param_idx}))"
                f") DESC"
            )
        elif name_param_idx:
            order_clause = f"ORDER BY word_similarity(LOWER(${name_param_idx}), LOWER(v.card_name)) DESC"
            collapse_order_clause = f"ORDER BY word_similarity(LOWER(${name_param_idx}), LOWER(card_name)) DESC"
        elif oracle_param_idx:
            order_clause = (
                f"ORDER BY ts_rank_cd(v.search_vector, "
                f"websearch_to_tsquery('english', ${oracle_param_idx})) DESC"
            )
            collapse_order_clause = (
                f"ORDER BY ts_rank_cd(search_vector, "
                f"websearch_to_tsquery('english', ${oracle_param_idx})) DESC"
            )
        else:
            _set_cols = {"released_at"}
            _price_cols = {"price"}
            _view_cols = {"card_name", "cmc", "rarity_name", "set_name", "set_code"}
            safe_sort_order = "DESC" if (sort_order or "").upper() == "DESC" else "ASC"
            if sort_by in _set_cols:
                order_clause = f"ORDER BY s.{sort_by} {safe_sort_order}"
                collapse_order_clause = f"ORDER BY {sort_by} {safe_sort_order}"
            elif sort_by in _price_cols:
                order_clause = f"ORDER BY psp.price {safe_sort_order} NULLS LAST"
                collapse_order_clause = f"ORDER BY sort_price {safe_sort_order} NULLS LAST"
            else:
                safe_sort_by = sort_by if sort_by in _view_cols else "card_name"
                order_clause = f"ORDER BY v.{safe_sort_by} {safe_sort_order}"
                collapse_order_clause = f"ORDER BY {safe_sort_by} {safe_sort_order}"

        # JOIN sets for released_at (not projected by the view) and to filter on date range.
        from_clause = (
            "FROM card_catalog.v_card_versions_complete v"
            " JOIN card_catalog.sets s ON s.set_id = v.set_id"
            " LEFT JOIN card_catalog.card_version_illustration cvi ON cvi.card_version_id = v.card_version_id"
            " LEFT JOIN pricing.mv_card_price_spark psp ON psp.card_version_id = v.card_version_id"  # mv_card_price_spark is keyed on card_version_id (one row per version) — no fan-out risk
        )

        # Outer ORDER BY for collapse mode — references subquery columns (no table prefix).
        if collapse:
            if name_param_idx and oracle_param_idx:
                outer_order = (
                    f"ORDER BY ("
                    f"word_similarity(LOWER(${name_param_idx}), LOWER(card_name)) + "
                    f"ts_rank_cd(search_vector, websearch_to_tsquery('english', ${oracle_param_idx}))"
                    f") DESC"
                )
            elif name_param_idx:
                outer_order = f"ORDER BY word_similarity(LOWER(${name_param_idx}), LOWER(card_name)) DESC"
            elif oracle_param_idx:
                outer_order = (
                    f"ORDER BY ts_rank_cd(search_vector, "
                    f"websearch_to_tsquery('english', ${oracle_param_idx})) DESC"
                )
            else:
                _set_cols = {"released_at"}
                _price_cols = {"price"}
                _view_cols = {"card_name", "cmc", "rarity_name", "set_name", "set_code"}
                safe_sort_order = "DESC" if (sort_order or "").upper() == "DESC" else "ASC"
                if sort_by in _set_cols:
                    outer_order = f"ORDER BY released_at {safe_sort_order}"
                elif sort_by in _price_cols:
                    outer_order = f"ORDER BY sort_price {safe_sort_order} NULLS LAST"
                else:
                    safe_sort_by = sort_by if sort_by in _view_cols else "card_name"
                    outer_order = f"ORDER BY {safe_sort_by} {safe_sort_order}"

        # search_vector is only needed in collapsed outer ORDER BY when oracle_text is used.
        sv_col = ", v.search_vector" if (collapse and oracle_param_idx) else ""

        base_select = f"""
                v.card_version_id,
                v.unique_card_id,
                v.card_name,
                v.rarity_name,
                v.set_name,
                v.set_code,
                v.cmc,
                v.oracle_text,
                v.promo_types,
                v.collector_number,
                v.is_digital AS digital,
                v.collector_number,
                v.promo_types,
                s.released_at,
                cvi.image_uris->>'normal' AS image_normal,
                psp.price AS sort_price
                {sv_col}"""

        if collapse:
            query = f"""
                SELECT * FROM (
                    SELECT DISTINCT ON (v.unique_card_id, v.set_code)
                        {base_select},
                        COUNT(*) OVER (PARTITION BY v.unique_card_id, v.set_code) AS version_count
                    {from_clause}
                    {where_clause}
                    ORDER BY v.unique_card_id, v.set_code,
                             cardinality(v.promo_types) ASC NULLS LAST,
                             v.collector_number ASC NULLS LAST
                ) _collapsed
                {outer_order}
                LIMIT ${counter} OFFSET ${counter + 1}
            """
        else:
            query = f"""
                SELECT
                    {base_select}
                {from_clause}
                {where_clause}
                {order_clause}
                LIMIT ${counter} OFFSET ${counter + 1}
            """
        values.extend([limit, offset])
        cards = await self.execute_query(query, tuple(values))

        card_ids = [row["card_version_id"] for row in cards]
        price_data = await self._fetch_prices_for_cards(card_ids)
        cards = [
            {**dict(row), **price_data.get(str(row["card_version_id"]), self._PRICE_DEFAULTS)}
            for row in cards
        ]

        if collapse:
            count_query = f"""
                SELECT COUNT(*) AS total_count FROM (
                    SELECT DISTINCT v.unique_card_id, v.set_code
                    {from_clause}
                    {where_clause}
                ) _c
            """
        else:
            count_query = f"""
                SELECT COUNT(*) AS total_count
                {from_clause}
                {where_clause}
            """
        count_values = values[:-2]
        count_result = await self.execute_query(count_query, tuple(count_values))
        total_count = count_result[0]["total_count"] if count_result else 0

        # Facet query uses facet_where_clause (excludes promo_type predicate) so
        # all promo types present in the base filter remain selectable even after
        # the user has already chosen one or more types.
        facet_query = f"""
            SELECT array_agg(DISTINCT pt ORDER BY pt) AS promo_type_facets
            FROM card_catalog.v_card_versions_complete v
            JOIN card_catalog.sets s ON s.set_id = v.set_id
            CROSS JOIN LATERAL unnest(v.promo_types) AS t(pt)
            {facet_where_clause}
        """
        facet_result = await self.execute_query(facet_query, tuple(values[:facet_val_stop]))
        promo_type_facets = (
            (facet_result[0]["promo_type_facets"] or []) if facet_result else []
        )

        # Rarity facet query uses rf_conditions (excludes rarity predicate) so
        # all rarities present in the current base filter remain visible even when
        # the user has already applied a rarity filter.
        rarity_facet_query = f"""
            SELECT array_agg(DISTINCT v.rarity_name ORDER BY v.rarity_name) AS rarity_facets
            FROM card_catalog.v_card_versions_complete v
            JOIN card_catalog.sets s ON s.set_id = v.set_id
            {rarity_facet_where}
        """
        rarity_result = await self.execute_query(rarity_facet_query, tuple(rf_values))
        rarity_facets = (rarity_result[0]["rarity_facets"] or []) if rarity_result else []

        return {
            "cards": cards,
            "total_count": total_count,
            "promo_type_facets": promo_type_facets,
            "rarity_facets": rarity_facets,
        }
    async def get_versions_in_set(self, unique_card_id: UUID, set_code: str) -> list[dict]:
        """All card_version rows for one (unique_card_id, set_code) pair — for the versions table."""
        sql = """
            SELECT
                v.card_version_id,
                v.unique_card_id,
                v.card_name,
                v.set_code,
                v.set_name,
                v.collector_number,
                v.promo_types,
                v.rarity_name,
                cvi.image_uris->>'normal' AS image_normal,
                ARRAY(
                    SELECT LOWER(cf.code)
                    FROM card_catalog.card_version_finish cvf
                    JOIN card_catalog.card_finished cf ON cf.finish_id = cvf.finish_id
                    WHERE cvf.card_version_id = v.card_version_id
                ) AS available_finishes
            FROM card_catalog.v_card_versions_complete v
            JOIN card_catalog.sets s ON s.set_id = v.set_id
            LEFT JOIN card_catalog.card_version_illustration cvi
                ON cvi.card_version_id = v.card_version_id
            WHERE v.unique_card_id = $1
              AND v.set_code = $2
            ORDER BY cardinality(v.promo_types) ASC NULLS LAST, v.collector_number ASC NULLS LAST
        """
        rows = await self.execute_query(sql, (unique_card_id, set_code))
        card_ids = [row["card_version_id"] for row in rows]
        price_data = await self._fetch_prices_for_cards(card_ids)
        return [
            {**dict(row), **price_data.get(str(row["card_version_id"]), self._PRICE_DEFAULTS)}
            for row in rows
        ]

    async def get_other_sets(self, unique_card_id: UUID) -> list[dict]:
        """One representative row per set for a given unique_card_id — for the Other Sets table."""
        sql = """
            SELECT * FROM (
                SELECT DISTINCT ON (v.set_code)
                    v.card_version_id,
                    v.unique_card_id,
                    v.card_name,
                    v.set_code,
                    v.set_name,
                    s.released_at,
                    cvi.image_uris->>'normal' AS image_normal,
                    COUNT(*) OVER (PARTITION BY v.set_code) AS version_count
                FROM card_catalog.v_card_versions_complete v
                JOIN card_catalog.sets s ON s.set_id = v.set_id
                LEFT JOIN card_catalog.card_version_illustration cvi
                    ON cvi.card_version_id = v.card_version_id
                WHERE v.unique_card_id = $1
                  AND v.layout_name NOT IN ('token', 'double_faced_token')
                ORDER BY v.set_code,
                         cardinality(v.promo_types) ASC NULLS LAST,
                         v.collector_number ASC NULLS LAST
            ) _sets
            ORDER BY released_at DESC NULLS LAST
        """
        rows = await self.execute_query(sql, (unique_card_id,))
        card_ids = [row["card_version_id"] for row in rows]
        price_data = await self._fetch_prices_for_cards(card_ids)
        return [
            {**dict(row), **price_data.get(str(row["card_version_id"]), self._PRICE_DEFAULTS)}
            for row in rows
        ]

    async def bulk_update_mtg_stock_ids(self, ids: dict[str, str]):
        if not ids:
            return 0  # or just return

        # build two parallel arrays
        scry_ids = list(ids.keys())
        stock_ids = list(ids.values())

        query = """
        WITH ids AS (
            SELECT
                (SELECT card_identifier_ref_id FROM card_identifier_ref WHERE identifier_name = 'scryfall_id')  AS scry_ref,
                (SELECT card_identifier_ref_id FROM card_identifier_ref WHERE identifier_name = 'mtg_stock_id') AS stock_ref
        ),
        data(scryfall_id, mtgstock_id) AS (
            SELECT * FROM unnest($1::TEXT[], $2::TEXT[])  -- zipped pairs
        )
        INSERT INTO card_external_identifier (card_identifier_ref_id, card_version_id, value)
        SELECT
            ids.stock_ref,                -- we are INSERTING mtg_stock_id ...
            cei.card_version_id,
            data.mtgstock_id
        FROM data
        CROSS JOIN ids
        JOIN card_external_identifier AS cei
        ON cei.card_identifier_ref_id = ids.scry_ref  -- ... using scryfall to resolve card_version
        AND cei.value::TEXT             = data.scryfall_id
        ON CONFLICT (card_identifier_ref_id, card_version_id)
        DO UPDATE SET value = EXCLUDED.value;
        """

        # Pass TWO params, not one
        await self.execute_command(query, (scry_ids, stock_ids))

    @dataclass(slots=True, frozen=True)
    class ExternalIdentifierRegistration:
        """Outcome of a single-row card_external_identifier upsert."""
        ref_found: bool
        card_version_exists: bool
        inserted: bool

    async def register_external_identifier(
        self,
        card_version_id: UUID,
        identifier_name: str,
        value: str,
    ) -> "CardReferenceRepository.ExternalIdentifierRegistration":
        """Idempotently register one (card_version, identifier_name, value) row via a single-CTE round-trip."""
        # ON CONFLICT targets the PK only. There is no UNIQUE (ref_id, value)
        # constraint — it was intentionally dropped so that shared identifiers
        # like tcgplayer_id and cardmarket_id can be owned by multiple
        # card_version rows (foil/non-foil pairs of the same physical product).
        # A duplicate (card_version_id, ref_id) row is silently absorbed; any
        # other combination inserts a new row, which is the correct behaviour.
        query = """
            WITH ref AS (
                SELECT card_identifier_ref_id
                FROM card_catalog.card_identifier_ref
                WHERE identifier_name = $2
            ),
            cv AS (
                SELECT card_version_id
                FROM card_catalog.card_version
                WHERE card_version_id = $1
            ),
            ins AS (
                INSERT INTO card_catalog.card_external_identifier (
                    card_version_id, card_identifier_ref_id, value
                )
                SELECT cv.card_version_id, ref.card_identifier_ref_id, $3
                FROM cv, ref
                ON CONFLICT (card_version_id, card_identifier_ref_id) DO NOTHING
                RETURNING 1
            )
            SELECT
                (SELECT card_identifier_ref_id FROM ref) IS NOT NULL AS ref_found,
                (SELECT card_version_id FROM cv)         IS NOT NULL AS card_version_exists,
                EXISTS (SELECT 1 FROM ins)                           AS inserted
        """
        rows = await self.execute_query(query, (card_version_id, identifier_name, value))
        row = rows[0] if rows else None
        if row is None:
            raise RuntimeError(
                "register_external_identifier: expected one result row, got none"
            )
        return CardReferenceRepository.ExternalIdentifierRegistration(
            ref_found=bool(row["ref_found"]),
            card_version_exists=bool(row["card_version_exists"]),
            inserted=bool(row["inserted"]),
        )

    async def copy_migrations(self, buffer):
        """
        Bulk-load Scryfall migration records into ``card_catalog.scryfall_migration``
        with idempotent semantics on the ``id`` primary key.

        PostgreSQL ``COPY`` is a raw bulk transport — it has no ``ON CONFLICT``
        clause. Copying straight into the target table would blow up on the
        second daily run the moment a duplicate ``id`` shows up. The correct
        fix lives at the I/O boundary that actually knows about the conflict,
        not in a retry flag on the Celery task.

        Pattern: **COPY-into-staging + INSERT … ON CONFLICT DO NOTHING**
        (a narrow application of the Unit of Work pattern).

            1. Open a transaction so staging DDL, COPY, and the promotion
               INSERT form a single atomic unit — on failure nothing leaks.
            2. ``CREATE TEMP TABLE … ON COMMIT DROP`` — session-scoped,
               self-cleaning on COMMIT. No housekeeping, no cross-run
               collision if asyncpg reuses the connection.
            3. COPY the TSV buffer into the temp table (fast path preserved).
            4. Promote with ``INSERT … SELECT … ON CONFLICT (id) DO NOTHING``
               so duplicates on re-run are a silent no-op — not a 500.

        The staging schema mirrors ``card_catalog.scryfall_migration`` *without*
        the PK so COPY never rejects a row mid-stream; the PK check happens
        at promotion time, where ``ON CONFLICT`` can absorb it cleanly.

        A "SELECT-then-INSERT" guard would be the wrong alternative: it's
        both racy under concurrent pipeline runs and strictly slower than
        letting the DB's conflict machinery do its job.
        """
        # Keep the staging columns aligned with the tab-separated line built
        # by ``ScryfallAPIRepository.migrations_to_bytes_buffer``:
        #   id, uri, performed_at, migration_strategy,
        #   old_scryfall_id, new_scryfall_id, note, created_at, updated_at
        staging_table = "tmp_scryfall_migration_stage"

        create_staging_sql = f"""
            CREATE TEMP TABLE IF NOT EXISTS {staging_table} (
                id                 uuid,
                uri                text,
                performed_at       date,
                migration_strategy text,
                old_scryfall_id    uuid,
                new_scryfall_id    uuid,
                note               text,
                created_at         timestamptz,
                updated_at         timestamptz
            ) ON COMMIT DROP
        """

        promote_sql = f"""
            INSERT INTO card_catalog.scryfall_migration (
                id, uri, performed_at, migration_strategy,
                old_scryfall_id, new_scryfall_id, note,
                created_at, updated_at
            )
            SELECT
                id, uri, performed_at, migration_strategy,
                old_scryfall_id, new_scryfall_id, note,
                created_at, updated_at
            FROM {staging_table}
            ON CONFLICT (id) DO NOTHING
        """

        data = buffer.getvalue()  # BytesIO -> bytes
        assert isinstance(data, (bytes, bytearray)), type(data)
        data_mv = memoryview(data)

        # Single transaction binds DDL + COPY + INSERT. If any step raises,
        # asyncpg rolls back; ``ON COMMIT DROP`` guarantees the temp table
        # evaporates on the happy path — no explicit DROP required.
        async with self.transaction():
            await self.execute_command(create_staging_sql)
            copy_status = await self.execute_copy_to_table(
                staging_table,
                data_mv,
                format="csv",
                null="",
                delimiter="\t",
                header=False,
            )
            insert_status = await self.execute_command(promote_sql)

        # Return both statuses — ``insert_status`` (e.g. "INSERT 0 N") is what
        # callers actually care about: rows that survived the conflict filter.
        # ``copy_status`` only reflects ingestion into the throwaway staging
        # table and is kept for observability/debugging.
        return {"copy_status": copy_status, "insert_status": insert_status}

    async def fetch_identifier_coverage_pct(self, identifier_name: str) -> dict | None:
        """Return per-identifier coverage stats for the card_catalog.identifier_coverage.* metrics.

        Returns ``{'covered': int, 'total': int, 'pct': float|None}``. ``pct`` is
        NULL when ``total`` is 0 — the metric layer treats NULL as Severity.WARN
        rather than silently passing.
        """
        query = """
        WITH totals AS (
            SELECT COUNT(*)::int AS total FROM card_catalog.card_version
        ),
        covered AS (
            SELECT COUNT(DISTINCT cei.card_version_id)::int AS covered
            FROM card_catalog.card_external_identifier cei
            JOIN card_catalog.card_identifier_ref cir
              ON cir.card_identifier_ref_id = cei.card_identifier_ref_id
            WHERE cir.identifier_name = $1
        )
        SELECT
            covered,
            total,
            CASE WHEN total = 0 THEN NULL
                 ELSE ROUND(100.0 * covered / total, 2)::float
            END AS pct
        FROM totals, covered
        """
        rows = await self.execute_query(query, (identifier_name,))
        return dict(rows[0]) if rows else None

    async def fetch_identifier_coverage_pct_by_unique_card(
        self, identifier_name: str
    ) -> dict | None:
        """Coverage measured against ``unique_cards_ref`` rather than ``card_version``.

        Use this for identifiers that are a property of the *abstract card* (one
        value per ``unique_card_id``) rather than per-printing — most notably
        ``oracle_id``. Because ``oracle_id`` is shared across every printing of
        the same abstract card, counting rows per ``card_version`` would
        under-report coverage by the average reprint rate (~3x for oracle_id),
        making the per-``card_version`` metric misleading for these identifiers.
        Note: the ``UNIQUE (card_identifier_ref_id, value)`` constraint no longer
        exists; multiple ``card_version`` rows can legally share one oracle_id value.

        Returns the same shape as :meth:`fetch_identifier_coverage_pct`:
        ``{'covered': int, 'total': int, 'pct': float|None}``. ``covered`` is
        the count of distinct ``unique_card_id`` values for which at least one
        ``card_version`` has a row of ``identifier_name`` in
        ``card_external_identifier``; ``total`` is the count of
        ``unique_cards_ref`` rows.
        """
        query = """
        WITH totals AS (
            SELECT COUNT(*)::int AS total FROM card_catalog.unique_cards_ref
        ),
        covered AS (
            SELECT COUNT(DISTINCT cv.unique_card_id)::int AS covered
            FROM card_catalog.card_external_identifier cei
            JOIN card_catalog.card_identifier_ref cir
              ON cir.card_identifier_ref_id = cei.card_identifier_ref_id
            JOIN card_catalog.card_version cv
              ON cv.card_version_id = cei.card_version_id
            WHERE cir.identifier_name = $1
        )
        SELECT
            covered,
            total,
            CASE WHEN total = 0 THEN NULL
                 ELSE ROUND(100.0 * covered / total, 2)::float
            END AS pct
        FROM totals, covered
        """
        rows = await self.execute_query(query, (identifier_name,))
        return dict(rows[0]) if rows else None

    async def fetch_identifier_value_count(self, identifier_name: str) -> int:
        """COUNT of card_version rows that have at least one row for ``identifier_name``.

        Used by the informational metrics (multiverse_id, tcgplayer_etched_id)
        which track raw counts rather than coverage percentages.
        """
        query = """
        SELECT COUNT(DISTINCT cei.card_version_id)::int AS n
        FROM card_catalog.card_external_identifier cei
        JOIN card_catalog.card_identifier_ref cir
          ON cir.card_identifier_ref_id = cei.card_identifier_ref_id
        WHERE cir.identifier_name = $1
        """
        rows = await self.execute_query(query, (identifier_name,))
        return rows[0]["n"] if rows else 0

    async def fetch_identifier_audit_counts(self) -> "list[dict]":
        """Per-identifier aggregate counts for the scryfall-vs-db audit service.

        One row per ``identifier_name`` registered in ``card_identifier_ref``.
        Identifiers with zero stored rows still appear (LEFT JOIN), so the audit
        can flag them.
        """
        query = """
        SELECT
            cir.identifier_name                               AS identifier_name,
            COUNT(cei.value)::int                             AS total_rows,
            COUNT(DISTINCT cei.value)::int                    AS distinct_values,
            COUNT(DISTINCT cei.card_version_id)::int          AS distinct_card_versions,
            COUNT(DISTINCT cv.unique_card_id)::int            AS distinct_unique_cards
        FROM card_catalog.card_identifier_ref cir
        LEFT JOIN card_catalog.card_external_identifier cei
               ON cei.card_identifier_ref_id = cir.card_identifier_ref_id
        LEFT JOIN card_catalog.card_version cv
               ON cv.card_version_id = cei.card_version_id
        GROUP BY cir.identifier_name
        ORDER BY cir.identifier_name
        """
        rows = await self.execute_query(query, ())
        return [dict(r) for r in rows]

    async def fetch_card_universe_counts(self) -> dict:
        """Denominator counts used by the scryfall-vs-db audit service."""
        query = """
        SELECT
            (SELECT COUNT(*)::int FROM card_catalog.card_version)      AS total_card_versions,
            (SELECT COUNT(*)::int FROM card_catalog.unique_cards_ref)  AS total_unique_cards
        """
        rows = await self.execute_query(query, ())
        return dict(rows[0]) if rows else {"total_card_versions": 0, "total_unique_cards": 0}

    async def update_purchase_uris_batch(
        self, rows: List[dict]  # [{scryfall_id, purchase_uris}]
    ) -> int:
        """Bulk-update purchase_uris on card_version rows identified by scryfall_id.

        Returns the number of rows updated.
        """
        if not rows:
            return 0

        scryfall_ids = [r["scryfall_id"] for r in rows]
        uri_jsons = [json.dumps(r["purchase_uris"]) for r in rows]

        sql = """
UPDATE card_catalog.card_version cv
SET
    purchase_uris = v.uris::jsonb,
    updated_at = now()
FROM unnest($1::text[], $2::text[]) AS v(scryfall_id, uris)
JOIN card_catalog.card_external_identifier ei ON ei.value = v.scryfall_id
JOIN card_catalog.card_identifier_ref ir ON ir.card_identifier_ref_id = ei.card_identifier_ref_id
    AND ir.identifier_name = 'scryfall_id'
WHERE cv.card_version_id = ei.card_version_id
"""
        status = await self.execute_command(sql, (scryfall_ids, uri_jsons))
        # status is like "UPDATE N"
        try:
            return int(status.split()[-1])
        except (IndexError, ValueError):
            return len(rows)

    async def fetch_orphan_unique_cards_count(self) -> int:
        """COUNT of unique_cards_ref rows with zero card_version children.

        Small counts are benign (tokens / emblems not yet printed); large
        counts indicate a mid-run set-ingest stall.
        """
        query = """
        SELECT COUNT(*)::int AS n
        FROM card_catalog.unique_cards_ref ucr
        WHERE NOT EXISTS (
            SELECT 1 FROM card_catalog.card_version cv
            WHERE cv.unique_card_id = ucr.unique_card_id
        )
        """
        rows = await self.execute_query(query, ())
        return rows[0]["n"] if rows else 0

    async def fetch_external_id_value_collisions(self) -> int:
        """COUNT of (card_identifier_ref_id, value) tuples shared by more than one
        card_version_id for identifiers that upstream guarantees are per-printing unique.

        The ``UNIQUE (card_identifier_ref_id, value)`` constraint was dropped intentionally
        to allow tcgplayer_id, cardmarket_id, and tcgplayer_etched_id to be shared by
        foil/non-foil (or ★/non-★) pairs of the same physical product.  Identifiers that
        are strictly one-per-printing — ``scryfall_id``, ``multiverse_id``, ``mtgjson_id``
        — should never collide.  Any non-zero count here indicates a real bug: either a
        duplicate ingest, a pipeline retry that produced duplicate rows, or an upstream
        data error that slipped past validation.

        Identifiers intentionally excluded (expected multi-card_version sharing):
        - oracle_id           — one value per abstract card, shared across all printings
        - tcgplayer_id        — one product per physical SKU; foil/non-foil pairs share
        - cardmarket_id       — same sharing pattern as tcgplayer_id
        - tcgplayer_etched_id — Secret Lair ★ variants share the same etched product ID
                                as the base variant (confirmed upstream behavior, not a bug)
        """
        query = """
        SELECT COUNT(*)::int AS n
        FROM (
            SELECT cei.card_identifier_ref_id, cei.value
            FROM card_catalog.card_external_identifier cei
            JOIN card_catalog.card_identifier_ref cir
              ON cir.card_identifier_ref_id = cei.card_identifier_ref_id
            WHERE cir.identifier_name IN (
                'scryfall_id', 'multiverse_id', 'mtgjson_id'
            )
            GROUP BY cei.card_identifier_ref_id, cei.value
            HAVING COUNT(DISTINCT cei.card_version_id) > 1
        ) dup
        """
        rows = await self.execute_query(query, ())
        return rows[0]["n"] if rows else 0

    async def get_price_history(
        self,
        card_version_id: UUID,
        start_date: date,
        end_date: date,
        finish: Optional[str] = None,
        aggregation: str = 'daily',
    ) -> Dict[str, Any]:
        """
        Fetch aggregated price history for a card across all sources.

        Args:
            card_version_id: Card version ID
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            finish: Optional finish code string ('NONFOIL', 'FOIL', 'ETCHED', etc.)
            aggregation: 'daily' or 'weekly' aggregation (default='daily')

        Returns:
            Dict with keys: list_avg, sold_avg, dates
            - list_avg: List[Optional[float]] with one entry per period (null-filled for missing data)
            - sold_avg: List[Optional[float]] with one entry per period (null-filled for missing data)
            - dates: List[date] with period start dates in order
        """
        finish_filter = ""
        params: list = [card_version_id, start_date, end_date]
        if finish:
            finish_filter = f"AND f.code = ${len(params) + 1}"
            params.append(finish.upper())

        if aggregation == 'weekly':
            query = f"""
            WITH weekly_range AS (
                SELECT generate_series(date_trunc('week', $2::date)::date, $3::date, interval '1 week')::date AS week_start
            ),
            tier2_prices AS (
                SELECT
                    date_trunc('week', ppd.price_date)::date AS week_start,
                    COALESCE(AVG(ppd.list_avg_cents), AVG(ppd.sold_avg_cents))::float / 100 AS list_avg_price,
                    AVG(ppd.sold_avg_cents)::float / 100 AS sold_avg_price
                FROM pricing.print_price_daily ppd
                JOIN card_catalog.card_finished f ON f.finish_id = ppd.finish_id
                WHERE ppd.card_version_id = $1
                  AND ppd.price_date >= $2
                  AND ppd.price_date <= $3
                  {finish_filter}
                GROUP BY date_trunc('week', ppd.price_date)
            ),
            tier3_prices AS (
                SELECT
                    ppw.price_week AS week_start,
                    COALESCE(AVG(ppw.list_avg_cents), AVG(ppw.sold_avg_cents))::float / 100 AS list_avg_price,
                    AVG(ppw.sold_avg_cents)::float / 100 AS sold_avg_price
                FROM pricing.print_price_weekly ppw
                JOIN card_catalog.card_finished f ON f.finish_id = ppw.finish_id
                WHERE ppw.card_version_id = $1
                  AND ppw.price_week >= $2
                  AND ppw.price_week <= $3
                  {finish_filter}
                GROUP BY ppw.price_week
            ),
            combined AS (
                SELECT week_start, list_avg_price, sold_avg_price FROM tier2_prices
                UNION ALL
                SELECT t3.week_start, t3.list_avg_price, t3.sold_avg_price
                FROM tier3_prices t3
                WHERE t3.week_start NOT IN (SELECT week_start FROM tier2_prices)
            )
            SELECT
                wr.week_start AS price_date,
                c.list_avg_price,
                c.sold_avg_price
            FROM weekly_range wr
            LEFT JOIN combined c ON wr.week_start = c.week_start
            ORDER BY wr.week_start ASC
            """
        else:
            query = f"""
            WITH date_range AS (
                SELECT generate_series($2::date, $3::date, interval '1 day')::date AS price_date
            ),
            daily_prices AS (
                SELECT
                    ppd.price_date,
                    COALESCE(AVG(ppd.list_avg_cents), AVG(ppd.sold_avg_cents))::float / 100 AS list_avg_price,
                    AVG(ppd.sold_avg_cents)::float / 100 AS sold_avg_price
                FROM pricing.print_price_daily ppd
                JOIN card_catalog.card_finished f ON f.finish_id = ppd.finish_id
                WHERE ppd.card_version_id = $1
                  AND ppd.price_date >= $2
                  AND ppd.price_date <= $3
                  {finish_filter}
                GROUP BY ppd.price_date
            )
            SELECT
                dr.price_date,
                dp.list_avg_price,
                dp.sold_avg_price
            FROM date_range dr
            LEFT JOIN daily_prices dp ON dr.price_date = dp.price_date
            ORDER BY dr.price_date ASC
            """

        rows = await self.execute_query(query, tuple(params))

        if not rows:
            return {
                "list_avg": [],
                "sold_avg": [],
                "dates": []
            }

        list_avg = [row["list_avg_price"] for row in rows]
        sold_avg = [row["sold_avg_price"] for row in rows]
        dates = [row["price_date"] for row in rows]

        return {
            "list_avg": list_avg,
            "sold_avg": sold_avg,
            "dates": dates
        }

    async def list(self, *_: Any, **__: Any):
        raise NotImplementedError
