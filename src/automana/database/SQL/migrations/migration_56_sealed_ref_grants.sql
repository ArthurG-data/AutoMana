-- migration_56: Fix grants and seed missing subtypes for sealed type ref tables.
--
-- migration_55 only granted SELECT on sealed_type_ref and sealed_subtype_ref.
-- The bootstrap service (pricing.sealed.bootstrap_catalog_from_set) auto-inserts
-- unknown type/subtype codes; it needs INSERT + UPDATE via app_rw (inherited by
-- both app_backend and app_celery).
--
-- Also seeds 'premium' and 'welcome' subtypes first observed in DSK (Duskmourn).

INSERT INTO card_catalog.sealed_subtype_ref (subtype_code) VALUES
    ('premium'),
    ('welcome')
ON CONFLICT (subtype_code) DO NOTHING;

GRANT INSERT, UPDATE ON card_catalog.sealed_type_ref    TO app_rw, app_admin;
GRANT INSERT, UPDATE ON card_catalog.sealed_subtype_ref TO app_rw, app_admin;
