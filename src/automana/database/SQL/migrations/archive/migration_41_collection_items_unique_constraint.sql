-- migration_41: enforce one entry per (collection, card version, finish, condition)
--
-- Prior to this migration, the same card could be inserted multiple times into
-- the same collection with identical (collection_id, unique_card_id, finish_id,
-- condition). This constraint closes that gap at the database level.
--
-- The INSERT in collection_repository.add_entry is updated to use
-- ON CONFLICT DO NOTHING so callers get back the existing row silently.

ALTER TABLE user_collection.collection_items
    ADD CONSTRAINT uq_collection_card_finish_condition
    UNIQUE (collection_id, unique_card_id, finish_id, condition);
