# MTGStock — Prints with No Resolvable Identifiers

**Date discovered:** 2026-04-26  
**Pipeline run:** mtg_stock_all run 3  
**Status:** Under investigation — these rows will always land in `pricing.stg_price_observation_reject`

## What We Found

After fixing the case-sensitivity bug in `load_staging_prices_batched` (migration 16),
the staging pipeline is expected to resolve ~84–88% of the 56,817 print_ids in
`pricing.raw_mtg_stock_price`. The remaining 22 prints listed here have **no
usable identifiers** in the MTGStocks export:

- `scryfall_id` is NULL
- `tcg_id` is NULL
- `cardtrader_id` is NULL
- `collector_number` is NULL

With no identifiers, all three resolution paths fail:
1. **PRINT_ID path** — `mtgstock_id` has never been mapped for these prints
2. **EXTERNAL_ID path** — no scryfall_id, tcgplayer_id, or cardtrader_id to cross-reference
3. **SET_COLLECTOR path** — requires a non-null `collector_number`

## The Unresolvable Prints

| print_id | card_name | set_abbr | Notes |
|----------|-----------|----------|-------|
| 16829 | Demon | DDC | Token from Duel Decks: Divine vs Demonic |
| 16946 | Elemental | EVG | Token from Elves vs Goblins |
| 16959 | Goblin | EVG | Token from Elves vs Goblins |
| 17322 | Saproling | DDE | Token from Duel Decks: Elves vs Insects |
| 17684 | Armored Pegasus | S00 | Starter 2000 |
| 17685 | Bog Imp | S00 | Starter 2000 |
| 17687 | Coercion | S00 | Starter 2000 |
| 17688 | Counterspell | S00 | Starter 2000 |
| 17689 | Disenchant | S00 | Starter 2000 |
| 17698 | Goblin Hero | S00 | Starter 2000 |
| 17700 | Hero's Resolve | S00 | Starter 2000 |
| 17702 | Island | S00 | Starter 2000 |
| 17706 | Merfolk of the Pearl Trident | S00 | Starter 2000 |
| 17711 | Obsianus Golem | S00 | Starter 2000 |
| 17715 | Prodigal Sorcerer | S00 | Starter 2000 |
| 17716 | Python | S00 | Starter 2000 |
| 17721 | Scathe Zombies | S00 | Starter 2000 |
| 17723 | Shock | S00 | Starter 2000 |
| 17726 | Stone Rain | S00 | Starter 2000 |
| 17728 | Terror | S00 | Starter 2000 |
| 17735 | Wind Drake | S00 | Starter 2000 |
| 56756 | Orah, Skyclave Hierophant | (null) | Missing set code entirely |

## Why They Lack Identifiers

MTGStocks tracks certain token cards and very old promotional printings that
predate widespread use of collector numbers. The MTGStocks data export simply
omits external IDs for these entries. Known categories:

- **Tokens** (e.g. `Demon`, `Elemental`, `Goblin`, `Saproling`): Token cards were not
  consistently tracked in Scryfall's early data. Their MTGStocks `info.json`
  files have `scryfallId: null` and `collector_number: null`. The Duel Decks
  tokens (DDC, EVG, DDE) are particularly problematic since MTGStocks uses
  different set codes than Scryfall's current classification.
- **Starter 2000 / S00 cards** (e.g. `Disenchant`, `Coercion`, `Goblin Hero`,
  `Wind Drake`): S00 is a regional set with incomplete identifier coverage
  in the MTGStocks export. These are regular playable cards, not tokens, but
  lack modern cross-references.
- **Orah, Skyclave Hierophant (print_id 56756)**: This is the most mysterious entry—
  the card has no set_code at all in the raw data, making it impossible to
  narrow down which printing it refers to. This may indicate corrupted or
  incomplete data in the MTGStocks export.

## Resolution Options

### Option A — Manual mtgstock_id backfill (recommended for resolvable cards)
1. Look up each print_id on the MTGStocks website (e.g. `https://www.mtgstocks.com/prints/<print_id>`).
2. Find the matching card in `card_catalog.card_version` (via name + set code).
3. Insert a row into `card_catalog.card_external_identifier`:
   ```sql
   INSERT INTO card_catalog.card_external_identifier
     (card_identifier_ref_id, card_version_id, value)
   SELECT cir.card_identifier_ref_id, '<card_version_id>', '<print_id>'
   FROM card_catalog.card_identifier_ref cir
   WHERE cir.identifier_name = 'mtgstock_id'
   ON CONFLICT DO NOTHING;
   ```
4. After inserting, mark the reject rows as resolvable by setting
   `is_terminal = FALSE` and clearing `terminal_reason` so `retry_rejects`
   picks them up.

### Option B — Mark as terminal (acceptable for cards not in catalog)
If a card genuinely doesn't exist in `card_catalog.card_version` (e.g. tokens
that Scryfall doesn't track), mark it terminal:
```sql
UPDATE pricing.stg_price_observation_reject
SET is_terminal = TRUE,
    terminal_reason = 'Token/legacy print: no identifier in MTGStocks export and no catalog entry'
WHERE print_id IN (<list of print_ids>);
```

### Option C — Add name+set fallback (not recommended)
Adding a 4th resolution path using `set_abbr + card_name` without
`collector_number` introduces ambiguity (many tokens share the same name
across sets). The "Goblin Token" vs "Goblin" naming divergence across data
sources compounds this. Only consider this if the number of affected prints
grows significantly.

## Next Steps

- [ ] Verify each print_id on mtgstocks.com and identify the canonical card
- [ ] For prints that exist in `card_catalog.card_version`, apply Option A
- [ ] For prints with no catalog entry, apply Option B
- [ ] Handle print_id 56756 (Orah) specially — investigate the data source
- [ ] After resolution, re-run `retry_rejects` to promote resolved rows
