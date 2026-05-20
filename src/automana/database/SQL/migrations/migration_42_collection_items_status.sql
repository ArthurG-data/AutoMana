-- migration_42: add status + eBay link to collection_items
--
-- status: purchased (default) | listed | stashed | sold
-- ebay_item_id: optional link to app_integration.ebay_active_listings.item_id
--   stored as plain TEXT (no FK) so purged eBay records don't cascade-break entries.
--   When ebay_item_id IS NOT NULL and the listing still exists with ended_at IS NULL,
--   the repository query auto-derives status = 'listed'.

ALTER TABLE user_collection.collection_items
    ADD COLUMN status     VARCHAR(10) NOT NULL DEFAULT 'purchased'
        CHECK (status IN ('purchased', 'listed', 'stashed', 'sold')),
    ADD COLUMN ebay_item_id TEXT NULL;

CREATE INDEX IF NOT EXISTS idx_collection_items_status
    ON user_collection.collection_items (status);
