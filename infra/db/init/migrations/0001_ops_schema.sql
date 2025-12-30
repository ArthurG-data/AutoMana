--add the main URL for scryfall as a source
INSERT INTO ops.sources (name, base_uri, rate_limit_hz, kind)
VALUES ('scryfall', 'https://api.scryfall.com', 100, 'http')
ON CONFLICT (name) DO NOTHING;
--add the bulk-data resource for scryfall
INSERT INTO ops.resources (source_id, external_type, external_id, name, api_uri, web_uri, description)
VALUES ((SELECT id FROM ops.sources WHERE name='scryfall'),
        'bulk_data',
        'all_bulk_data',
        'Scryfall All Cards Bulk Data',
        '/bulk-data',
        'https://api.scryfall.com/bulk-data',
        'Bulk data manifest of all Magic: The Gathering cards from Scryfall')
--add the scryfall sets
INSERT INTO ops.resources (source_id, external_type, external_id, name, api_uri, web_uri, description)
VALUES ((SELECT id FROM ops.sources WHERE name='scryfall'),
        'bulk_set_data',
        'all_sets',
        'Scryfall All Sets Bulk Data',
        '/sets',
        'https://api.scryfall.com/sets',
        'Bulk data of all Magic: The Gathering sets from Scryfall')