
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
                BEGIN;
                WITH 
                delete_card_version AS (
                DELETE FROM card_catalog.card_version WHERE card_version_id = %s ON CASCADE
                RETURNING unique_card_id AS deleted_card_id
                ),
                DELETE FROM unique_card_ref 
                    WHERE unique_card_id IN (
                        SELECT deleted_card_id FROM delete_card_version
                    )
                    AND NOT EXISTS (
                        SELECT 1 FROM card_version
                        WHERE card_id IN (
                            SELECT deleted_card_id FROM delete_card_version
                    )
                );
                COMMIT;
"""