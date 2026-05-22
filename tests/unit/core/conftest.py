"""Shared fixtures for unit tests in tests/unit/core/."""
import pytest


@pytest.fixture
def scryfall_card():
    return {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "oracle_id": "550e8400-e29b-41d4-a716-446655440001",
        "name": "Lightning Bolt",
        "lang": "en",
        "released_at": "1993-08-05",
        "layout": "normal",
        "mana_cost": "{R}",
        "cmc": 1.0,
        "type_line": "Instant",
        "oracle_text": "Lightning Bolt deals 3 damage to any target.",
        "color_identity": ["R"],
        "legalities": {"standard": "not_legal", "modern": "legal"},
        "games": ["paper"],
        "set": "lea",
        "set_name": "Limited Edition Alpha",
        "set_id": "550e8400-e29b-41d4-a716-446655440002",
        "collector_number": "162",
        "rarity": "common",
        "artist": "Christopher Rush",
        "artist_ids": ["550e8400-e29b-41d4-a716-446655440003"],
        "illustration_id": "550e8400-e29b-41d4-a716-446655440004",
        "border_color": "black",
        "frame": "1993",
        "full_art": False,
        "textless": False,
        "booster": True,
        "promo": False,
        "digital": False,
        "finishes": ["nonfoil"],
        "prices": {
            "usd": "1.50",
            "usd_foil": None,
            "usd_etched": None,
            "eur": "1.20",
            "eur_foil": None,
            "tix": "0.05",
        },
        "purchase_uris": {
            "tcgplayer": "https://www.tcgplayer.com/product/12345",
            "cardmarket": "https://www.cardmarket.com/en/Magic/Products/Singles/Alpha/Lightning-Bolt",
        },
    }


@pytest.fixture
def scryfall_dfc_card():
    """Double-faced card fixture — transforms layout with card_faces."""
    return {
        "id": "660e8400-e29b-41d4-a716-446655440000",
        "oracle_id": "660e8400-e29b-41d4-a716-446655440001",
        "name": "Delver of Secrets // Insectile Aberration",
        "lang": "en",
        "released_at": "2011-09-30",
        "layout": "transform",
        "cmc": 1.0,
        "color_identity": ["U"],
        "legalities": {"standard": "not_legal", "modern": "legal"},
        "games": ["paper"],
        "set": "isd",
        "set_name": "Innistrad",
        "set_id": "660e8400-e29b-41d4-a716-446655440002",
        "collector_number": "51",
        "rarity": "uncommon",
        "artist": "Nils Hamm",
        "artist_ids": ["660e8400-e29b-41d4-a716-446655440003"],
        "border_color": "black",
        "frame": "2015",
        "full_art": False,
        "textless": False,
        "booster": True,
        "promo": False,
        "digital": False,
        "finishes": ["nonfoil", "foil"],
        "card_faces": [
            {
                "name": "Delver of Secrets",
                "mana_cost": "{U}",
                "type_line": "Creature — Human Wizard",
                "oracle_text": "At the beginning of your upkeep...",
                "illustration_id": "660e8400-e29b-41d4-a716-446655440010",
                "image_uris": {"normal": "https://cards.scryfall.io/normal/front/..."},
            },
            {
                "name": "Insectile Aberration",
                "mana_cost": "",
                "type_line": "Creature — Human Insect",
                "oracle_text": "Flying",
                "image_uris": {"normal": "https://cards.scryfall.io/normal/back/..."},
            },
        ],
        "prices": {"usd": "2.00", "usd_foil": "5.00", "eur": "1.80", "tix": "0.10"},
    }


@pytest.fixture
def scryfall_set():
    return {
        "id": "770e8400-e29b-41d4-a716-446655440000",
        "name": "Limited Edition Alpha",
        "code": "lea",
        "type": "core",
        "released_at": "1993-08-05",
        "digital": False,
        "nonfoil_only": True,
        "foil_only": False,
        "parent_set_code": None,
        "icon_svg_uri": "https://svgs.scryfall.io/sets/lea.svg",
    }


@pytest.fixture
def scryfall_bulk_manifest_items():
    return [
        {
            "id": "bulk-001",
            "type": "all_cards",
            "name": "All Cards",
            "description": "Every card object on Scryfall in every language.",
            "uri": "https://api.scryfall.com/bulk-data/bulk-001",
            "download_uri": "https://data.scryfall.io/all-cards/all-cards-20250101.json",
            "updated_at": "2025-01-01T00:00:00.000Z",
            "size": 500000000,
            "content_type": "application/json",
            "content_encoding": "gzip",
        },
        {
            "id": "bulk-002",
            "type": "oracle_cards",
            "name": "Oracle Cards",
            "description": "One card object per Oracle ID.",
            "uri": "https://api.scryfall.com/bulk-data/bulk-002",
            "download_uri": "https://data.scryfall.io/oracle-cards/oracle-cards-20250101.json",
            "updated_at": "2025-01-01T00:00:00.000Z",
            "size": 50000000,
            "content_type": "application/json",
            "content_encoding": "gzip",
        },
    ]


@pytest.fixture
def scryfall_migration_row():
    return {
        "id": "mig-abc123",
        "uri": "https://api.scryfall.com/migrations/mig-abc123",
        "performed_at": "2025-01-15",
        "migration_strategy": "merge",
        "old_scryfall_id": "old-scryfall-uuid",
        "new_scryfall_id": "new-scryfall-uuid",
        "note": "Cards were merged into a single printing.",
    }
