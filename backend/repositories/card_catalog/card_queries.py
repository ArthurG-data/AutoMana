
insert_full_card_query = """
        SELECT insert_full_card_version(
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
        $14, -- colors
        $15, -- artist
        $16, -- artist_id

        -- Game properties (17-22)
        $17, -- legalities
        $18, -- illustration_id
        $19, -- types
        $20, -- supertypes
        $21, -- subtypes
        $22, -- games
        
        -- Print properties (23-28)
        $23, -- oversized
        $24, -- booster
        $25, -- full_art
        $26, -- textless
        $27, -- power
        $28, -- toughness
        $29, -- loyalty
        $30, -- defense

        -- Additional data (29-33)
        $31, -- promo_types
        $32, -- variation
        $33 -- card_faces
    );
"""

insert_batch_card_query = """
    SELECT * FROM insert_batch_card_versions($1::JSONB);
"""

delete_card_query = """
                BEGIN;
                WITH 
                delete_card_version AS (
                DELETE FROM card_version WHERE card_version_id = %s ON CASCADE
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