
main_insert_query = """  WITH 
                ins_unique_card AS (INSERT INTO unique_cards_ref (card_name, cmc, mana_cost, reserved)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (card_name) DO NOTHING
                            RETURNING unique_card_id),
                get_card_id AS 
                           (SELECT unique_card_id FROM ins_unique_card
                            UNION
                            SELECT unique_card_id FROM unique_cards_ref WHERE card_name = %s),
                ins_border_color AS (
                            INSERT INTO border_color_ref (border_color_name)
                            VALUES (%s)
                            ON CONFLICT (border_color_name) DO NOTHING
                            RETURNING border_color_id
                ),
                get_border_id AS (
                           SELECT border_color_id FROM ins_border_color
                           UNION
                           SELECT border_color_id FROM border_color_ref WHERE border_color_name = %s
                           ),
                ins_rarity AS (
                            INSERT INTO rarities_ref (rarity_name)
                            VALUES (%s)
                            ON CONFLICT (rarity_name) DO NOTHING
                            RETURNING rarity_id
                ),
                get_rarity_id AS (
                            SELECT rarity_id FROM ins_rarity
                            UNION
                            SELECT rarity_id FROM rarities_ref WHERE rarity_name = %s
                ),
                ins_artist AS (
                            INSERT INTO artists_ref (artist_name)
                            VALUES (%s)
                            ON CONFLICT (artist_name) DO NOTHING
                            RETURNING artist_id
                ),
                get_artist_id AS (
                            SELECT artist_id FROM ins_artist
                            UNION
                            SELECT artist_id FROM artists_ref WHERE artist_name = %s
                ),
                ins_frame AS (
                            INSERT INTO frames_ref (frame_year)
                            VALUES (%s)
                            ON CONFLICT (frame_year) DO NOTHING
                            RETURNING frame_id
                ),
                get_frame_id AS (
                            SELECT frame_id FROM ins_frame
                            UNION
                            SELECT frame_id FROM frames_ref WHERE frame_year = %s
                ),
                ins_layout AS (
                            INSERT INTO layouts_ref (layout_name)
                            VALUES (%s)
                            ON CONFLICT (layout_name) DO NOTHING
                            RETURNING layout_id 
                ),
                get_layout_id AS (
                            SELECT layout_id FROM ins_layout
                            UNION
                            SELECT layout_id FROM layouts_ref WHERE layout_name = %s
                ),
                get_set_id AS (
                            SELECT set_id FROM sets WHERE set_name = %s
                ),
                insert_card_version AS (
                    INSERT INTO card_version (
                        unique_card_id, oracle_text, 
                        set_id, collector_number, 
                        rarity_id, border_color_id,
                        frame_id, layout_id, 
                        is_promo, is_digital
                    )
                    SELECT 
                        guc.unique_card_id, %s, gs.set_id, %s, gr.rarity_id, 
                        gb.border_color_id, gf.frame_id, gl.layout_id, %s,
                        %s
                    FROM get_card_id guc
                    CROSS JOIN get_set_id gs
                    CROSS JOIN get_rarity_id gr
                    CROSS JOIN get_border_id gb
                    CROSS JOIN get_frame_id gf
                    CROSS JOIN get_layout_id gl
                    RETURNING card_version_id
                )
                SELECT card_version_id FROM insert_card_version;
        
              """
