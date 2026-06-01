-- migration_28_card_back_id.sql
-- Add card_back_id column to card_version table to support card back imagery

ALTER TABLE card_catalog.card_version
  ADD COLUMN IF NOT EXISTS card_back_id UUID;
