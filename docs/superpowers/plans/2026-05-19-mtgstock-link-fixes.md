# MTGStock Link Rate Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add ART_CARD and TOKEN_NAME resolution paths to the MTGStock pricing procedures so that art card and token price rows stop being rejected on future pipeline runs.

**Architecture:** Two mapping tables already exist and need seed data (`pricing.mtgstock_art_set_map`, `pricing.mtgstock_token_set_map`). Two SQL procedures need new CTEs/temp tables appended after the existing SET_COLLECTOR path: `pricing.load_staging_prices_batched` and `pricing.resolve_price_rejects`. Changes go into `06_prices.sql` (canonical) and `migration_40_mtgstock_link_fixes.sql` (live DB).

**Tech Stack:** PostgreSQL stored procedures (plpgsql), temp tables, CTEs, `REGEXP_REPLACE`, `SPLIT_PART`, `DISTINCT ON`.

---

## File Map

| File | Change |
|------|--------|
| `src/automana/database/SQL/schemas/06_prices.sql` | Add seed INSERTs; extend both procedures |
| `src/automana/database/SQL/migrations/migration_40_mtgstock_link_fixes.sql` | Create — applies seeds + `CREATE OR REPLACE` for both procedures |

No Python files change. No tests exist for these procedures; verification is via SQL queries after applying the migration.

---

## Task 1: Seed mtgstock_art_set_map and mtgstock_token_set_map in 06_prices.sql

**Files:**
- Modify: `src/automana/database/SQL/schemas/06_prices.sql:84-93`

- [ ] **Step 1: Replace the 8-row art set INSERT with the full 39-row version**

In `06_prices.sql`, find and replace:

```sql
INSERT INTO pricing.mtgstock_art_set_map (mtgstocks_set_code, scryfall_set_code) VALUES
    ('AAINR', 'ainr'),
    ('ADFT',  'adft'),
    ('AEOE',  'aeoe'),
    ('AFIN',  'afin'),
    ('AATDM', 'aatdm'),
    ('ASLD',  'asld'),
    ('APRE',  'apre'),
    ('AMAT',  'amat')
ON CONFLICT (mtgstocks_set_code) DO NOTHING;
```

With:

```sql
INSERT INTO pricing.mtgstock_art_set_map (mtgstocks_set_code, scryfall_set_code) VALUES
    ('AAINR', 'ainr'),
    ('ADFT',  'adft'),
    ('AEOE',  'aeoe'),
    ('AFIN',  'afin'),
    ('AATDM', 'aatdm'),
    ('ASLD',  'asld'),
    ('APRE',  'apre'),
    ('AMAT',  'amat'),
    ('AACR',  'aacr'),
    ('AAFR',  'aafr'),
    ('ABLB',  'ablb'),
    ('ABRO',  'abro'),
    ('ACLB',  'aclb'),
    ('ACMM',  'acmm'),
    ('ADMU',  'admu'),
    ('ADSK',  'adsk'),
    ('AECL',  'aecl'),
    ('AFDN',  'afdn'),
    ('AJMP',  'ajmp'),
    ('AKHM',  'akhm'),
    ('ALCI',  'alci'),
    ('ALTC',  'altc'),
    ('ALTR',  'altr'),
    ('AMH1',  'amh1'),
    ('AMH2',  'amh2'),
    ('AMH3',  'amh3'),
    ('AMID',  'amid'),
    ('AMKM',  'amkm'),
    ('AMOM',  'amom'),
    ('ANEO',  'aneo'),
    ('AONE',  'aone'),
    ('AOTJ',  'aotj'),
    ('ASNC',  'asnc'),
    ('ASOS',  'asos'),
    ('ASPM',  'aspm'),
    ('ASTX',  'astx'),
    ('ATDM',  'atdm'),
    ('ATLA',  'atla'),
    ('ATLE',  'atle'),
    ('ATMT',  'atmt'),
    ('AVOW',  'avow'),
    ('AWOE',  'awoe'),
    ('AZNR',  'aznr')
ON CONFLICT (mtgstocks_set_code) DO NOTHING;
```

- [ ] **Step 2: Add the token set INSERT immediately after the art set INSERT**

After the art set `ON CONFLICT ... DO NOTHING;` line, insert:

```sql
INSERT INTO pricing.mtgstock_token_set_map (mtgstocks_set_code, token_set_code) VALUES
    ('10E', 't10e'), ('2X2', 't2x2'), ('2XM', 't2xm'), ('30A', 't30a'),
    ('40K', 't40k'), ('A25', 'ta25'), ('ACR', 'tacr'), ('AER', 'taer'),
    ('AFC', 'tafc'), ('AFR', 'tafr'), ('AKH', 'takh'), ('ALA', 'tala'),
    ('ARB', 'tarb'), ('AVR', 'tavr'), ('BBD', 'tbbd'), ('BFZ', 'tbfz'),
    ('BIG', 'tbig'), ('BLB', 'tblb'), ('BLC', 'tblc'), ('BNG', 'tbng'),
    ('BOT', 'tbot'), ('BRC', 'tbrc'), ('BRO', 'tbro'), ('C14', 'tc14'),
    ('C15', 'tc15'), ('C16', 'tc16'), ('C17', 'tc17'), ('C18', 'tc18'),
    ('C19', 'tc19'), ('C20', 'tc20'), ('C21', 'tc21'), ('CLB', 'tclb'),
    ('CM2', 'tcm2'), ('CMA', 'tcma'), ('CMM', 'tcmm'), ('CMR', 'tcmr'),
    ('CN2', 'tcn2'), ('CNS', 'tcns'), ('CON', 'tcon'), ('DD1', 'tdd1'),
    ('DD2', 'tdd2'), ('DDC', 'tddc'), ('DDD', 'tddd'), ('DDE', 'tdde'),
    ('DDF', 'tddf'), ('DDG', 'tddg'), ('DDH', 'tddh'), ('DDI', 'tddi'),
    ('DDJ', 'tddj'), ('DDK', 'tddk'), ('DDL', 'tddl'), ('DDM', 'tddm'),
    ('DDS', 'tdds'), ('DDT', 'tddt'), ('DDU', 'tddu'), ('DFT', 'tdft'),
    ('DGM', 'tdgm'), ('DKA', 'tdka'), ('DMC', 'tdmc'), ('DMR', 'tdmr'),
    ('DMU', 'tdmu'), ('DOM', 'tdom'), ('DRC', 'tdrc'), ('DSC', 'tdsc'),
    ('DSK', 'tdsk'), ('DTK', 'tdtk'), ('DVD', 'tdvd'), ('E01', 'te01'),
    ('ECC', 'tecc'), ('ECL', 'tecl'), ('ELD', 'teld'), ('EMA', 'tema'),
    ('EMN', 'temn'), ('EOC', 'teoc'), ('EOE', 'teoe'), ('EVE', 'teve'),
    ('EVG', 'tevg'), ('FDN', 'tfdn'), ('FIC', 'tfic'), ('FIN', 'tfin'),
    ('FRF', 'tfrf'), ('GK1', 'tgk1'), ('GK2', 'tgk2'), ('GN2', 'tgn2'),
    ('GN3', 'tgn3'), ('GRN', 'tgrn'), ('GTC', 'tgtc'), ('GVL', 'tgvl'),
    ('HOB', 'thob'), ('HOU', 'thou'), ('IKO', 'tiko'), ('IMA', 'tima'),
    ('INR', 'tinr'), ('ISD', 'tisd'), ('JOU', 'tjou'), ('JVC', 'tjvc'),
    ('KHC', 'tkhc'), ('KHM', 'tkhm'), ('KLD', 'tkld'), ('KTK', 'tktk'),
    ('LCC', 'tlcc'), ('LCI', 'tlci'), ('LRW', 'tlrw'), ('LTC', 'tltc'),
    ('LTR', 'tltr'), ('M10', 'tm10'), ('M11', 'tm11'), ('M12', 'tm12'),
    ('M13', 'tm13'), ('M14', 'tm14'), ('M15', 'tm15'), ('M19', 'tm19'),
    ('M20', 'tm20'), ('M21', 'tm21'), ('M3C', 'tm3c'), ('MBS', 'tmbs'),
    ('MD1', 'tmd1'), ('MED', 'tmed'), ('MH1', 'tmh1'), ('MH2', 'tmh2'),
    ('MH3', 'tmh3'), ('MIC', 'tmic'), ('MID', 'tmid'), ('MKC', 'tmkc'),
    ('MKM', 'tmkm'), ('MM2', 'tmm2'), ('MM3', 'tmm3'), ('MMA', 'tmma'),
    ('MOC', 'tmoc'), ('MOM', 'tmom'), ('MOR', 'tmor'), ('MSH', 'tmsh'),
    ('MUL', 'tmul'), ('NCC', 'tncc'), ('NEC', 'tnec'), ('NEO', 'tneo'),
    ('NPH', 'tnph'), ('OGW', 'togw'), ('ONC', 'tonc'), ('ONE', 'tone'),
    ('ORI', 'tori'), ('OTC', 'totc'), ('OTJ', 'totj'), ('OTP', 'totp'),
    ('PCA', 'tpca'), ('PIP', 'tpip'), ('REX', 'trex'), ('RIX', 'trix'),
    ('RNA', 'trna'), ('ROE', 'troe'), ('RTR', 'trtr'), ('RVR', 'trvr'),
    ('SCD', 'tscd'), ('SHM', 'tshm'), ('SNC', 'tsnc'), ('SOC', 'tsoc'),
    ('SOI', 'tsoi'), ('SOM', 'tsom'), ('SOS', 'tsos'), ('SPM', 'tspm'),
    ('STX', 'tstx'), ('TDC', 'ttdc'), ('TDM', 'ttdm'), ('THB', 'tthb'),
    ('THS', 'tths'), ('TLA', 'ttla'), ('TLE', 'ttle'), ('TMC', 'ttmc'),
    ('TMT', 'ttmt'), ('TSR', 'ttsr'), ('UGL', 'tugl'), ('UMA', 'tuma'),
    ('UND', 'tund'), ('UNF', 'tunf'), ('UST', 'tust'), ('VOC', 'tvoc'),
    ('VOW', 'tvow'), ('WAR', 'twar'), ('WHO', 'twho'), ('WOC', 'twoc'),
    ('WOE', 'twoe'), ('WWK', 'twwk'), ('XLN', 'txln'), ('ZEN', 'tzen'),
    ('ZNC', 'tznc'), ('ZNR', 'tznr')
ON CONFLICT (mtgstocks_set_code) DO NOTHING;
```

- [ ] **Step 3: Commit**

```bash
git add src/automana/database/SQL/schemas/06_prices.sql
git commit -m "feat(pricing): seed mtgstock_art_set_map (39 rows) and mtgstock_token_set_map (186 rows)"
```

---

## Task 2: Extend load_staging_prices_batched with ART_CARD and TOKEN_NAME paths

**Files:**
- Modify: `src/automana/database/SQL/schemas/06_prices.sql` (inside `load_staging_prices_batched`)

The procedure lives between `CREATE OR REPLACE PROCEDURE pricing.load_staging_prices_batched` and its closing `$$`. The `tmp_map_fallback` block ends around line 1142. The `tmp_resolved` block is immediately after.

- [ ] **Step 1: Add tmp_map_art and tmp_map_tok after tmp_map_fallback**

Find this exact block (end of `tmp_map_fallback`):

```sql
  WHERE u.set_abbr IS NOT NULL
    AND u.collector_number IS NOT NULL
    AND (
        u.card_name IS NULL
        OR uc.card_name IS NULL
        OR lower(uc.card_name) = lower(u.card_name)
        OR lower(u.card_name) LIKE (lower(uc.card_name) || ' (%')
    );

  -- 3d) Final resolved rows
```

Replace with:

```sql
  WHERE u.set_abbr IS NOT NULL
    AND u.collector_number IS NOT NULL
    AND (
        u.card_name IS NULL
        OR uc.card_name IS NULL
        OR lower(uc.card_name) = lower(u.card_name)
        OR lower(u.card_name) LIKE (lower(uc.card_name) || ' (%')
    );

  -- (4) art card resolution: lookup via mtgstock_art_set_map, match by collector_number only
  DROP TABLE IF EXISTS tmp_map_art;
  CREATE TEMP TABLE tmp_map_art ON COMMIT DROP AS
  SELECT DISTINCT
    u.print_id,
    cv.card_version_id
  FROM tmp_raw_batch u
  JOIN pricing.mtgstock_art_set_map asm
    ON asm.mtgstocks_set_code = UPPER(u.set_abbr)
  JOIN card_catalog.sets s
    ON s.set_code = asm.scryfall_set_code
  JOIN card_catalog.card_version cv
    ON cv.set_id = s.set_id
   AND cv.collector_number::text = u.collector_number
  WHERE u.set_abbr IS NOT NULL
    AND u.collector_number IS NOT NULL;

  -- (5) token resolution: strip Token suffix, split double-sided faces, match by name
  DROP TABLE IF EXISTS tmp_map_tok;
  CREATE TEMP TABLE tmp_map_tok ON COMMIT DROP AS
  SELECT DISTINCT ON (u.print_id)
    u.print_id,
    cv.card_version_id
  FROM tmp_raw_batch u
  JOIN pricing.mtgstock_token_set_map tsm
    ON tsm.mtgstocks_set_code = UPPER(u.set_abbr)
  JOIN card_catalog.sets s
    ON s.set_code = tsm.token_set_code
  JOIN card_catalog.card_version cv
    ON cv.set_id = s.set_id
  WHERE u.set_abbr IS NOT NULL
    AND u.collector_number IS NULL
    AND u.card_name IS NOT NULL
    AND (
      cv.name ILIKE SPLIT_PART(REGEXP_REPLACE(u.card_name, '\s*(Token|Double-Sided Token)$', '', 'i'), ' // ', 1)
      OR (
        SPLIT_PART(REGEXP_REPLACE(u.card_name, '\s*(Token|Double-Sided Token)$', '', 'i'), ' // ', 2) <> ''
        AND cv.name ILIKE SPLIT_PART(REGEXP_REPLACE(u.card_name, '\s*(Token|Double-Sided Token)$', '', 'i'), ' // ', 2)
      )
    )
  ORDER BY u.print_id, cv.card_version_id;

  -- 3d) Final resolved rows
```

- [ ] **Step 2: Extend tmp_resolved to include the two new paths**

Find:

```sql
  DROP TABLE IF EXISTS tmp_resolved;
  CREATE TEMP TABLE tmp_resolved ON COMMIT DROP AS
  SELECT
    u.*,
    COALESCE(mp.card_version_id, me.card_version_id, mf.card_version_id) AS card_version_id,
    CASE
      WHEN mp.card_version_id IS NOT NULL THEN 'PRINT_ID'
      WHEN me.card_version_id IS NOT NULL THEN 'EXTERNAL_ID'
      WHEN mf.card_version_id IS NOT NULL THEN 'SET_COLLECTOR'
      ELSE 'UNRESOLVED'
    END AS resolution_method
  FROM tmp_batch_foil_split u
  LEFT JOIN tmp_map_print mp
    ON mp.print_id = u.print_id
  LEFT JOIN tmp_map_external me
    ON me.print_id = u.print_id
  LEFT JOIN tmp_map_fallback mf
    ON mf.set_abbr = u.set_abbr
  AND mf.collector_number = u.collector_number;
```

Replace with:

```sql
  DROP TABLE IF EXISTS tmp_resolved;
  CREATE TEMP TABLE tmp_resolved ON COMMIT DROP AS
  SELECT
    u.*,
    COALESCE(mp.card_version_id, me.card_version_id, mf.card_version_id, ma.card_version_id, mt.card_version_id) AS card_version_id,
    CASE
      WHEN mp.card_version_id IS NOT NULL THEN 'PRINT_ID'
      WHEN me.card_version_id IS NOT NULL THEN 'EXTERNAL_ID'
      WHEN mf.card_version_id IS NOT NULL THEN 'SET_COLLECTOR'
      WHEN ma.card_version_id IS NOT NULL THEN 'ART_CARD'
      WHEN mt.card_version_id IS NOT NULL THEN 'TOKEN_NAME'
      ELSE 'UNRESOLVED'
    END AS resolution_method
  FROM tmp_batch_foil_split u
  LEFT JOIN tmp_map_print mp
    ON mp.print_id = u.print_id
  LEFT JOIN tmp_map_external me
    ON me.print_id = u.print_id
  LEFT JOIN tmp_map_fallback mf
    ON mf.set_abbr = u.set_abbr
   AND mf.collector_number = u.collector_number
  LEFT JOIN tmp_map_art ma
    ON ma.print_id = u.print_id
  LEFT JOIN tmp_map_tok mt
    ON mt.print_id = u.print_id;
```

- [ ] **Step 3: Commit**

```bash
git add src/automana/database/SQL/schemas/06_prices.sql
git commit -m "feat(pricing): add ART_CARD and TOKEN_NAME resolution to load_staging_prices_batched"
```

---

## Task 3: Extend resolve_price_rejects with ART_CARD and TOKEN_NAME paths

**Files:**
- Modify: `src/automana/database/SQL/schemas/06_prices.sql` (inside `resolve_price_rejects`)

- [ ] **Step 1: Add v_art_card and v_token_name to DECLARE block**

Find:

```sql
  v_set_collector   bigint := 0;
  v_unresolved      bigint := 0;
```

Replace with:

```sql
  v_set_collector   bigint := 0;
  v_art_card        bigint := 0;
  v_token_name      bigint := 0;
  v_unresolved      bigint := 0;
```

- [ ] **Step 2: Add map_art and map_tok CTEs after map_fb, extend COALESCE/CASE/JOINs**

Find (the closing of map_fb and the final SELECT):

```sql
      AND (
          r.card_name IS NULL
          OR uc.card_name IS NULL
          OR lower(uc.card_name) = lower(r.card_name)
          OR lower(r.card_name) LIKE (lower(uc.card_name) || ' (%')
      )
  )
  SELECT
    r.*,
    COALESCE(mp.card_version_id, me.card_version_id, mf.card_version_id) AS card_version_id,
    CASE
      WHEN mp.card_version_id IS NOT NULL THEN 'PRINT_ID'
      WHEN me.card_version_id IS NOT NULL THEN 'EXTERNAL_ID'
      WHEN mf.card_version_id IS NOT NULL THEN 'SET_COLLECTOR'
      ELSE 'UNRESOLVED'
    END AS resolution_method
  FROM tmp_rejects r
  LEFT JOIN map_print mp ON mp.print_id = r.print_id
  LEFT JOIN map_ext   me ON me.print_id = r.print_id
  LEFT JOIN map_fb    mf ON mf.set_abbr = r.set_abbr AND mf.collector_number = r.collector_number;
```

Replace with:

```sql
      AND (
          r.card_name IS NULL
          OR uc.card_name IS NULL
          OR lower(uc.card_name) = lower(r.card_name)
          OR lower(r.card_name) LIKE (lower(uc.card_name) || ' (%')
      )
  ),
  map_art AS (
    SELECT DISTINCT r.print_id, cv.card_version_id
    FROM tmp_rejects r
    JOIN pricing.mtgstock_art_set_map asm
      ON asm.mtgstocks_set_code = UPPER(r.set_abbr)
    JOIN card_catalog.sets s
      ON s.set_code = asm.scryfall_set_code
    JOIN card_catalog.card_version cv
      ON cv.set_id = s.set_id
     AND cv.collector_number::text = r.collector_number
    WHERE r.set_abbr IS NOT NULL
      AND r.collector_number IS NOT NULL
  ),
  map_tok AS (
    SELECT DISTINCT ON (r.print_id)
      r.print_id, cv.card_version_id
    FROM tmp_rejects r
    JOIN pricing.mtgstock_token_set_map tsm
      ON tsm.mtgstocks_set_code = UPPER(r.set_abbr)
    JOIN card_catalog.sets s
      ON s.set_code = tsm.token_set_code
    JOIN card_catalog.card_version cv
      ON cv.set_id = s.set_id
    WHERE r.set_abbr IS NOT NULL
      AND r.collector_number IS NULL
      AND r.card_name IS NOT NULL
      AND (
        cv.name ILIKE SPLIT_PART(REGEXP_REPLACE(r.card_name, '\s*(Token|Double-Sided Token)$', '', 'i'), ' // ', 1)
        OR (
          SPLIT_PART(REGEXP_REPLACE(r.card_name, '\s*(Token|Double-Sided Token)$', '', 'i'), ' // ', 2) <> ''
          AND cv.name ILIKE SPLIT_PART(REGEXP_REPLACE(r.card_name, '\s*(Token|Double-Sided Token)$', '', 'i'), ' // ', 2)
        )
      )
    ORDER BY r.print_id, cv.card_version_id
  )
  SELECT
    r.*,
    COALESCE(mp.card_version_id, me.card_version_id, mf.card_version_id, ma.card_version_id, mt.card_version_id) AS card_version_id,
    CASE
      WHEN mp.card_version_id IS NOT NULL THEN 'PRINT_ID'
      WHEN me.card_version_id IS NOT NULL THEN 'EXTERNAL_ID'
      WHEN mf.card_version_id IS NOT NULL THEN 'SET_COLLECTOR'
      WHEN ma.card_version_id IS NOT NULL THEN 'ART_CARD'
      WHEN mt.card_version_id IS NOT NULL THEN 'TOKEN_NAME'
      ELSE 'UNRESOLVED'
    END AS resolution_method
  FROM tmp_rejects r
  LEFT JOIN map_print mp ON mp.print_id = r.print_id
  LEFT JOIN map_ext   me ON me.print_id = r.print_id
  LEFT JOIN map_fb    mf ON mf.set_abbr = r.set_abbr AND mf.collector_number = r.collector_number
  LEFT JOIN map_art   ma ON ma.print_id = r.print_id
  LEFT JOIN map_tok   mt ON mt.print_id = r.print_id;
```

- [ ] **Step 3: Update the COUNT and RAISE NOTICE block**

Find:

```sql
  SELECT
    COUNT(*) FILTER (WHERE resolution_method = 'PRINT_ID'),
    COUNT(*) FILTER (WHERE resolution_method = 'EXTERNAL_ID'),
    COUNT(*) FILTER (WHERE resolution_method = 'SET_COLLECTOR'),
    COUNT(*) FILTER (WHERE resolution_method = 'UNRESOLVED')
  INTO v_print_id, v_external_id, v_set_collector, v_unresolved
  FROM tmp_resolved;
  RAISE NOTICE 'resolve_price_rejects: PRINT_ID=% EXTERNAL_ID=% SET_COLLECTOR=% UNRESOLVED=%',
    v_print_id, v_external_id, v_set_collector, v_unresolved;
```

Replace with:

```sql
  SELECT
    COUNT(*) FILTER (WHERE resolution_method = 'PRINT_ID'),
    COUNT(*) FILTER (WHERE resolution_method = 'EXTERNAL_ID'),
    COUNT(*) FILTER (WHERE resolution_method = 'SET_COLLECTOR'),
    COUNT(*) FILTER (WHERE resolution_method = 'ART_CARD'),
    COUNT(*) FILTER (WHERE resolution_method = 'TOKEN_NAME'),
    COUNT(*) FILTER (WHERE resolution_method = 'UNRESOLVED')
  INTO v_print_id, v_external_id, v_set_collector, v_art_card, v_token_name, v_unresolved
  FROM tmp_resolved;
  RAISE NOTICE 'resolve_price_rejects: PRINT_ID=% EXTERNAL_ID=% SET_COLLECTOR=% ART_CARD=% TOKEN_NAME=% UNRESOLVED=%',
    v_print_id, v_external_id, v_set_collector, v_art_card, v_token_name, v_unresolved;
```

- [ ] **Step 4: Commit**

```bash
git add src/automana/database/SQL/schemas/06_prices.sql
git commit -m "feat(pricing): add ART_CARD and TOKEN_NAME resolution to resolve_price_rejects"
```

---

## Task 4: Write migration_40_mtgstock_link_fixes.sql and apply to live DB

**Files:**
- Create: `src/automana/database/SQL/migrations/migration_40_mtgstock_link_fixes.sql`

- [ ] **Step 1: Create migration_40 file**

Create `src/automana/database/SQL/migrations/migration_40_mtgstock_link_fixes.sql` with:

```sql
BEGIN;

-- Seed art set map (adds 35 new rows; 8 existing rows are no-ops via ON CONFLICT)
INSERT INTO pricing.mtgstock_art_set_map (mtgstocks_set_code, scryfall_set_code) VALUES
    ('AAINR', 'ainr'),
    ('ADFT',  'adft'),
    ('AEOE',  'aeoe'),
    ('AFIN',  'afin'),
    ('AATDM', 'aatdm'),
    ('ASLD',  'asld'),
    ('APRE',  'apre'),
    ('AMAT',  'amat'),
    ('AACR',  'aacr'),
    ('AAFR',  'aafr'),
    ('ABLB',  'ablb'),
    ('ABRO',  'abro'),
    ('ACLB',  'aclb'),
    ('ACMM',  'acmm'),
    ('ADMU',  'admu'),
    ('ADSK',  'adsk'),
    ('AECL',  'aecl'),
    ('AFDN',  'afdn'),
    ('AJMP',  'ajmp'),
    ('AKHM',  'akhm'),
    ('ALCI',  'alci'),
    ('ALTC',  'altc'),
    ('ALTR',  'altr'),
    ('AMH1',  'amh1'),
    ('AMH2',  'amh2'),
    ('AMH3',  'amh3'),
    ('AMID',  'amid'),
    ('AMKM',  'amkm'),
    ('AMOM',  'amom'),
    ('ANEO',  'aneo'),
    ('AONE',  'aone'),
    ('AOTJ',  'aotj'),
    ('ASNC',  'asnc'),
    ('ASOS',  'asos'),
    ('ASPM',  'aspm'),
    ('ASTX',  'astx'),
    ('ATDM',  'atdm'),
    ('ATLA',  'atla'),
    ('ATLE',  'atle'),
    ('ATMT',  'atmt'),
    ('AVOW',  'avow'),
    ('AWOE',  'awoe'),
    ('AZNR',  'aznr')
ON CONFLICT (mtgstocks_set_code) DO NOTHING;

-- Seed token set map (186 rows)
INSERT INTO pricing.mtgstock_token_set_map (mtgstocks_set_code, token_set_code) VALUES
    ('10E', 't10e'), ('2X2', 't2x2'), ('2XM', 't2xm'), ('30A', 't30a'),
    ('40K', 't40k'), ('A25', 'ta25'), ('ACR', 'tacr'), ('AER', 'taer'),
    ('AFC', 'tafc'), ('AFR', 'tafr'), ('AKH', 'takh'), ('ALA', 'tala'),
    ('ARB', 'tarb'), ('AVR', 'tavr'), ('BBD', 'tbbd'), ('BFZ', 'tbfz'),
    ('BIG', 'tbig'), ('BLB', 'tblb'), ('BLC', 'tblc'), ('BNG', 'tbng'),
    ('BOT', 'tbot'), ('BRC', 'tbrc'), ('BRO', 'tbro'), ('C14', 'tc14'),
    ('C15', 'tc15'), ('C16', 'tc16'), ('C17', 'tc17'), ('C18', 'tc18'),
    ('C19', 'tc19'), ('C20', 'tc20'), ('C21', 'tc21'), ('CLB', 'tclb'),
    ('CM2', 'tcm2'), ('CMA', 'tcma'), ('CMM', 'tcmm'), ('CMR', 'tcmr'),
    ('CN2', 'tcn2'), ('CNS', 'tcns'), ('CON', 'tcon'), ('DD1', 'tdd1'),
    ('DD2', 'tdd2'), ('DDC', 'tddc'), ('DDD', 'tddd'), ('DDE', 'tdde'),
    ('DDF', 'tddf'), ('DDG', 'tddg'), ('DDH', 'tddh'), ('DDI', 'tddi'),
    ('DDJ', 'tddj'), ('DDK', 'tddk'), ('DDL', 'tddl'), ('DDM', 'tddm'),
    ('DDS', 'tdds'), ('DDT', 'tddt'), ('DDU', 'tddu'), ('DFT', 'tdft'),
    ('DGM', 'tdgm'), ('DKA', 'tdka'), ('DMC', 'tdmc'), ('DMR', 'tdmr'),
    ('DMU', 'tdmu'), ('DOM', 'tdom'), ('DRC', 'tdrc'), ('DSC', 'tdsc'),
    ('DSK', 'tdsk'), ('DTK', 'tdtk'), ('DVD', 'tdvd'), ('E01', 'te01'),
    ('ECC', 'tecc'), ('ECL', 'tecl'), ('ELD', 'teld'), ('EMA', 'tema'),
    ('EMN', 'temn'), ('EOC', 'teoc'), ('EOE', 'teoe'), ('EVE', 'teve'),
    ('EVG', 'tevg'), ('FDN', 'tfdn'), ('FIC', 'tfic'), ('FIN', 'tfin'),
    ('FRF', 'tfrf'), ('GK1', 'tgk1'), ('GK2', 'tgk2'), ('GN2', 'tgn2'),
    ('GN3', 'tgn3'), ('GRN', 'tgrn'), ('GTC', 'tgtc'), ('GVL', 'tgvl'),
    ('HOB', 'thob'), ('HOU', 'thou'), ('IKO', 'tiko'), ('IMA', 'tima'),
    ('INR', 'tinr'), ('ISD', 'tisd'), ('JOU', 'tjou'), ('JVC', 'tjvc'),
    ('KHC', 'tkhc'), ('KHM', 'tkhm'), ('KLD', 'tkld'), ('KTK', 'tktk'),
    ('LCC', 'tlcc'), ('LCI', 'tlci'), ('LRW', 'tlrw'), ('LTC', 'tltc'),
    ('LTR', 'tltr'), ('M10', 'tm10'), ('M11', 'tm11'), ('M12', 'tm12'),
    ('M13', 'tm13'), ('M14', 'tm14'), ('M15', 'tm15'), ('M19', 'tm19'),
    ('M20', 'tm20'), ('M21', 'tm21'), ('M3C', 'tm3c'), ('MBS', 'tmbs'),
    ('MD1', 'tmd1'), ('MED', 'tmed'), ('MH1', 'tmh1'), ('MH2', 'tmh2'),
    ('MH3', 'tmh3'), ('MIC', 'tmic'), ('MID', 'tmid'), ('MKC', 'tmkc'),
    ('MKM', 'tmkm'), ('MM2', 'tmm2'), ('MM3', 'tmm3'), ('MMA', 'tmma'),
    ('MOC', 'tmoc'), ('MOM', 'tmom'), ('MOR', 'tmor'), ('MSH', 'tmsh'),
    ('MUL', 'tmul'), ('NCC', 'tncc'), ('NEC', 'tnec'), ('NEO', 'tneo'),
    ('NPH', 'tnph'), ('OGW', 'togw'), ('ONC', 'tonc'), ('ONE', 'tone'),
    ('ORI', 'tori'), ('OTC', 'totc'), ('OTJ', 'totj'), ('OTP', 'totp'),
    ('PCA', 'tpca'), ('PIP', 'tpip'), ('REX', 'trex'), ('RIX', 'trix'),
    ('RNA', 'trna'), ('ROE', 'troe'), ('RTR', 'trtr'), ('RVR', 'trvr'),
    ('SCD', 'tscd'), ('SHM', 'tshm'), ('SNC', 'tsnc'), ('SOC', 'tsoc'),
    ('SOI', 'tsoi'), ('SOM', 'tsom'), ('SOS', 'tsos'), ('SPM', 'tspm'),
    ('STX', 'tstx'), ('TDC', 'ttdc'), ('TDM', 'ttdm'), ('THB', 'tthb'),
    ('THS', 'tths'), ('TLA', 'ttla'), ('TLE', 'ttle'), ('TMC', 'ttmc'),
    ('TMT', 'ttmt'), ('TSR', 'ttsr'), ('UGL', 'tugl'), ('UMA', 'tuma'),
    ('UND', 'tund'), ('UNF', 'tunf'), ('UST', 'tust'), ('VOC', 'tvoc'),
    ('VOW', 'tvow'), ('WAR', 'twar'), ('WHO', 'twho'), ('WOC', 'twoc'),
    ('WOE', 'twoe'), ('WWK', 'twwk'), ('XLN', 'txln'), ('ZEN', 'tzen'),
    ('ZNC', 'tznc'), ('ZNR', 'tznr')
ON CONFLICT (mtgstocks_set_code) DO NOTHING;
```

Then append the full `CREATE OR REPLACE PROCEDURE pricing.load_staging_prices_batched` body (copy it verbatim from `06_prices.sql` as updated by Task 2), followed by the full `CREATE OR REPLACE FUNCTION pricing.resolve_price_rejects` body (copy from `06_prices.sql` as updated by Task 3), then close with `COMMIT;`.

> **Note:** Do not paraphrase — copy the exact procedure text from the updated `06_prices.sql`. The procedure bodies are ~600 and ~400 lines respectively.

- [ ] **Step 2: Apply the migration to the live DB**

```bash
docker exec -i automana-postgres-dev psql -U automana_admin automana < src/automana/database/SQL/migrations/migration_40_mtgstock_link_fixes.sql
```

Expected: no errors, output ends with `COMMIT`.

- [ ] **Step 3: Verify seeds applied**

```bash
docker exec automana-postgres-dev psql -U automana_admin automana -c "
SELECT COUNT(*) AS art_rows  FROM pricing.mtgstock_art_set_map;
SELECT COUNT(*) AS token_rows FROM pricing.mtgstock_token_set_map;"
```

Expected: `art_rows = 43` (8 original + 35 new), `token_rows = 186`.

> **Note:** The count is 43 not 39 because the INSERT includes the original 8 rows (which become no-ops via `ON CONFLICT DO NOTHING`) plus 35 new ones, but the mapping table may have more entries than Scryfall's pure "Tokens" sets depending on prior manual inserts. Adjust expectation if prior manual rows exist.

Actually, the art set INSERT has exactly 43 rows total (8 original + 35 new). Run:
```bash
docker exec automana-postgres-dev psql -U automana_admin automana -c "SELECT COUNT(*) FROM pricing.mtgstock_art_set_map;"
```
Expected: `43`.

- [ ] **Step 4: Verify procedures compiled without error**

```bash
docker exec automana-postgres-dev psql -U automana_admin automana -c "
SELECT routine_name, routine_type
FROM information_schema.routines
WHERE routine_schema = 'pricing'
  AND routine_name IN ('load_staging_prices_batched', 'resolve_price_rejects');"
```

Expected: 2 rows returned (both routines exist).

- [ ] **Step 5: Smoke-test name-stripping SQL**

```bash
docker exec automana-postgres-dev psql -U automana_admin automana -c "
SELECT
  REGEXP_REPLACE('Atraxa Art Card (Gold-Stamped Signature)', ' Art Card.*\$', '', 'i') AS art_strip,
  REGEXP_REPLACE('Wolf // Demon Double-Sided Token', '\s*(Token|Double-Sided Token)\$', '', 'i') AS tok_strip,
  SPLIT_PART(REGEXP_REPLACE('Wolf // Demon Double-Sided Token', '\s*(Token|Double-Sided Token)\$', '', 'i'), ' // ', 1) AS face1,
  SPLIT_PART(REGEXP_REPLACE('Wolf // Demon Double-Sided Token', '\s*(Token|Double-Sided Token)\$', '', 'i'), ' // ', 2) AS face2;"
```

Expected:
```
 art_strip | tok_strip     | face1 | face2
-----------+---------------+-------+-------
 Atraxa    | Wolf // Demon | Wolf  | Demon
```

- [ ] **Step 6: Commit**

```bash
git add src/automana/database/SQL/migrations/migration_40_mtgstock_link_fixes.sql
git commit -m "feat(pricing): migration_40 — art card and token resolution fixes (Fix 2 + Fix 3)"
```

---

## Task 5: Update MTGSTOCK_REJECT_ANALYSIS.md and PIPELINE_TECHNICAL_DEBT.md

**Files:**
- Modify: `docs/MTGSTOCK_REJECT_ANALYSIS.md`
- Modify: `docs/PIPELINE_TECHNICAL_DEBT.md`

- [ ] **Step 1: Update the remaining fix plan table in MTGSTOCK_REJECT_ANALYSIS.md**

Find the `## Remaining fix plan` table and mark Fix 2 and Fix 3 as done:

```markdown
| Priority | Fix | Rows recoverable | Effort | Status |
|---|---|---|---|---|
| ~~1~~ | ~~Foil-treatment name suffix~~ | ~~403 K~~ | ~~1 SQL line + migration~~ | ✅ **Done** (271 803 rows, 2026-04-29) |
| ~~2~~ | ~~Art card set-code + name mapping~~ | ~~680 K~~ | ~~Mapping table + new `map_art` CTE~~ | ✅ **Done** (migration_40, 2026-05-19) |
| ~~3~~ | ~~Token resolution via `mtgstock_token_set_map`~~ | ~~3.8 M~~ | ~~New mapping table + 4th resolution path~~ | ✅ **Done** (migration_40, 2026-05-19) |
| — | No-set-abbr + old tokens + catalog gaps | 0–small | Structurally blocked / requires upstream data | Blocked |
```

- [ ] **Step 2: Update progress log in MTGSTOCK_REJECT_ANALYSIS.md**

Add a row to the progress log table:

```markdown
| 2026-05-19 | **Fix 2** — art card set-code mapping (map_art CTE) + **Fix 3** — token name resolution (map_tok CTE) | pending next run | pending next run |
```

- [ ] **Step 3: Update PIPELINE_TECHNICAL_DEBT.md debt items for Fix 2 + Fix 3**

Find the debt item for `mtgstock.cards_rejected` and update its `fix_notes` and `status`:

```
- **Fix**: Fix 2 and Fix 3 implemented in migration_40 (2026-05-19). Re-run `mtgStock_download_pipeline` to process new data through the updated procedures.
- **Status**: resolved
```

Find the debt item for `mtgstock.link_rate_pct` and update similarly:

```
- **Fix**: ART_CARD + TOKEN_NAME resolution paths added in migration_40 (2026-05-19).
- **Status**: resolved
```

- [ ] **Step 4: Commit**

```bash
git add docs/MTGSTOCK_REJECT_ANALYSIS.md docs/PIPELINE_TECHNICAL_DEBT.md
git commit -m "docs(pricing): mark Fix 2 + Fix 3 as done in reject analysis and debt tracker"
```
