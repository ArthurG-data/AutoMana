import json
import uuid
import os

# Where to save files
output_folder = "database_startup/test_files"
os.makedirs(output_folder, exist_ok=True)

# Template for card with faces
def generate_card_with_faces(i):
    return {
        "name": f"Test Card {i} (Faces)",
        "set_name": "Marvel's Spider-Man Tokens",
        "set": "tspm",
        "set_id" : str(uuid.uuid4()),
        "cmc": i % 5,
        "rarity": "common",
        "digital": False,
        "promo": False,
        "mana_cost": f"{{{i}}}",
        "collector_number": str(i),
        "border_color": "black",
        "frame": "2015",
        "layout": "normal",
        "keywords": [],
        "type_line": "Creature — Test",
        "oversized": False,
        "produced_mana": None,
        "color_identity": ["U"],
        "legalities": {
            "standard": "legal",
            "modern": "legal"
        },
        "supertypes": [],
        "types": ["Creature"],
        "subtypes": ["Test"],
        "booster": True,
        "full_art": False,
        "textless": False,
        "power": "1",
        "toughness": "1",
        "lang": "en",
        "promo_types": [],
        "variation": False,
        "reserved": False,
        "games": ["paper", "arena"],
        "artist": "Test Artist",
        "artist_ids": [str(uuid.uuid4())],
        "illustration_id": str(uuid.uuid4()),
        "card_faces": [
            {
                "name": f"Test Card {i} Front",
                "mana_cost": f"{{{i}}}",
                "type_line": "Creature — Test",
                "oracle_text": "Flying",
                "power": "1",
                "toughness": "1",
                "artist": "Test Artist",
                "artist_id": str(uuid.uuid4()),
                "illustration_id": str(uuid.uuid4()),
                "supertypes": [],
                "types": ["Creature"],
                "subtypes": ["Test"]
            },
            {
                "name": f"Test Card {i} Back",
                "mana_cost": f"{{{i}}}",
                "type_line": "Instant",
                "oracle_text": "Draw a card.",
                "artist": "Test Artist",
                "artist_id": str(uuid.uuid4()),
                "illustration_id": str(uuid.uuid4()),
                "supertypes": [],
                "types": ["Instant"],
                "subtypes": []
            }
        ]
    }

# Template for card with no faces (just type_line)
def generate_card_no_faces(i):
    return {
        "name": f"Test Card {i} (No Faces)",
        "set_name": "Marvel's Spider-Man Tokens",
        "set": "tspm",
        "set_id" : str(uuid.uuid4()),
        "cmc": i % 5,
        "rarity": "uncommon",
        "digital": False,
        "promo": False,
        "mana_cost": f"{{{i}}}",
        "collector_number": str(i),
        "border_color": "black",
        "frame": "2015",
        "layout": "normal",
        "keywords": [],
        "type_line": "Enchantment — Test",
        "oversized": False,
        "produced_mana": None,
        "color_identity": ["U"],
        "legalities": {
            "standard": "legal",
            "modern": "legal"
        },
        "supertypes": [],
        "types": ["Enchantment"],
        "subtypes": ["Test"],
        "booster": True,
        "full_art": False,
        "textless": False,
        "power": None,
        "toughness": None,
        "lang": "en",
        "promo_types": [],
        "variation": False,
        "reserved": False,
        "games": ["paper", "arena"],
        "artist": "Test Artist",
        "artist_ids": [str(uuid.uuid4())],
        "illustration_id": str(uuid.uuid4()),
        "card_faces": []  # Explicitly empty
    }

# Generate 200 cards for each type
cards_faces = [generate_card_with_faces(i) for i in range(1, 201)]
cards_no_faces = [generate_card_no_faces(i) for i in range(1, 201)]

# Save files
with open(os.path.join(output_folder, "test_cards_200_faces.json"), "w", encoding="utf-8") as f:
    json.dump(cards_faces, f, indent=2)

with open(os.path.join(output_folder, "test_cards_200_no_faces.json"), "w", encoding="utf-8") as f:
    json.dump(cards_no_faces, f, indent=2)

print("✅ Generated test_cards_200_faces.json and test_cards_200_no_faces.json.")
