-- Add mtgstock_id as a recognized external identifier type.
-- Enables card_external_identifier to store print_id -> card_version_id links.
INSERT INTO card_catalog.card_identifier_ref (identifier_name)
VALUES ('mtgstock_id')
ON CONFLICT (identifier_name) DO NOTHING;
