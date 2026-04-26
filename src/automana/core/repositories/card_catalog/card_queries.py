
insert_full_card_query = """
        SELECT card_catalog.insert_full_card_version(
        -- Basic card info (1-5)
        $1,  -- card_name
        $2,  -- cmc
        $3,  -- mana_cost
        $4,  -- reserved
        $5,  -- oracle_text
        
        -- Set and printing info (6-12)
        $6,  -- set_name
        $7,  -- collector_number
        $8,  -- rarity_name
        $9,  -- border_color
        $10, -- frame_year
        $11, -- layout_name
        $12, -- is_promo

        -- Display properties (13-16)
        $13, -- is_digital
        $14, --keywords
        $15, -- colors
        $16, -- artist
        $17, -- artist_id

        -- Game properties (17-22)
        $18, -- legalities
        $19, -- illustration_id
        $20, -- types
        $21, -- supertypes
        $22, -- subtypes
        $23, -- games
        
        -- Print properties (24-29)
        $24, -- oversized
        $25, -- booster
        $26, -- full_art
        $27, -- textless
        $28, -- power
        $29, -- toughness
        $30, -- loyalty
        $31, -- defense

        -- Additional data (32-36)
        $32, -- promo_types
        $33, -- variation
        $34, -- card_faces

        $35, --p_image_uris
        $36, -- scryfall_id
        $37, -- oracle_id
        $38, -- multiverse_ids
        $39, -- tcgplayer_id
        $40, -- tcgplayer_etched_id
        $41 -- cardmarket_id        
    );
"""

insert_batch_card_query = """
    SELECT * FROM card_catalog.insert_batch_card_versions($1::JSONB);
"""

delete_card_query = """
    WITH
    del_stats    AS (DELETE FROM card_catalog.card_version_stats        WHERE card_version_id = $1),
    del_illus    AS (DELETE FROM card_catalog.card_version_illustration  WHERE card_version_id = $1),
    del_games    AS (DELETE FROM card_catalog.games_card_version         WHERE card_version_id = $1),
    del_promo    AS (DELETE FROM card_catalog.promo_card                 WHERE card_version_id = $1),
    del_faces    AS (DELETE FROM card_catalog.card_faces                 WHERE card_version_id = $1),
    del_ext_id   AS (DELETE FROM card_catalog.card_external_identifier   WHERE card_version_id = $1),
    del_products AS (DELETE FROM pricing.mtg_card_products               WHERE card_version_id = $1),
    del_prices_d AS (DELETE FROM pricing.print_price_daily               WHERE card_version_id = $1),
    del_prices_w AS (DELETE FROM pricing.print_price_weekly              WHERE card_version_id = $1),
    deleted_version AS (
        DELETE FROM card_catalog.card_version
        WHERE card_version_id = $1
        RETURNING unique_card_id
    ),
    del_unique AS (
        DELETE FROM card_catalog.unique_cards_ref
        WHERE unique_card_id IN (SELECT unique_card_id FROM deleted_version)
          AND NOT EXISTS (
              SELECT 1 FROM card_catalog.card_version
              WHERE unique_card_id IN (SELECT unique_card_id FROM deleted_version)
                AND card_version_id != $1
          )
    )
    SELECT unique_card_id FROM deleted_version
"""