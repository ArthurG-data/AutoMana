-- migration_44: allow multiple copies of the same card per collection
--
-- The unique constraint (collection_id, unique_card_id, finish_id, condition)
-- prevented a user from owning more than one physical copy of the same printing
-- in the same condition. Dropping it lets each INSERT create a new independent
-- row, enabling per-copy price/date/status tracking.
--
-- Existing rows are unaffected — they were already unique before this migration.

ALTER TABLE user_collection.collection_items
    DROP CONSTRAINT uq_collection_card_finish_condition;
