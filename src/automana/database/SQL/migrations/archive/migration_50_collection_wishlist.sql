-- migration_50: add is_wishlist flag to collection_items
--
-- Separates intent (do I own this card vs do I want it) from lifecycle status
-- (purchased → listed → sold → stashed). Portfolio excludes is_wishlist=TRUE rows.
-- All existing rows default to FALSE (owned).

ALTER TABLE user_collection.collection_items
    ADD COLUMN IF NOT EXISTS is_wishlist BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_collection_items_wishlist
    ON user_collection.collection_items (is_wishlist);
