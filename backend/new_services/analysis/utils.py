from typing import Dict
import re

condition_variations = {
    "Near Mint": [
        "near mint", "nm", "n/m", "nearmint", "near-mint", 
        "mint", "m", "pristine", "perfect"
    ],
    "Lightly Played": [
        "lightly played", "light played", "lightly play", "light play",
        "lighlty played", "lighly played", "lighty played", "lightley played",
        "lp", "l/p", "light", "slightly played", "sp"
    ],
    "Moderately Played": [
        "moderately played", "moderate played", "moderatly played", 
        "mod played", "mp", "m/p", "moderate", "fair"
    ],
    "Heavily Played": [
        "heavily played", "heavy played", "heavly played", "heavily play",
        "hp", "h/p", "heavy", "poor", "damaged played"
    ],
    "Damaged": [
        "damaged", "dmg", "d", "broken", "destroyed", "poor condition",
        "badly damaged", "very poor", "vp"
    ],
    "Graded": [
        "graded", "psa", "bgs", "cgc", "beckett", "professional graded",
        "gem mint", "gm", "authenticated"
    ],
    "Sealed": [
        "sealed", "factory sealed", "new sealed", "unopened", 
        "mint sealed", "brand new"
    ]
}

def create_condition_pattern_map() -> Dict[str, str]:
    """Create a mapping of regex patterns to standard condition names"""
    pattern_map = {}
    
    for standard_condition, variations in condition_variations.items():
        for variation in variations:
            # Create flexible pattern that handles:
            # - Case insensitive
            # - Optional spaces, hyphens, slashes
            # - Common typos
            pattern = variation.lower()
            pattern = pattern.replace(" ", r"\s*")  # Optional spaces
            pattern = pattern.replace("-", r"[-\s]*")  # Optional hyphens/spaces
            pattern = pattern.replace("/", r"[/\s]*")  # Optional slashes/spaces
            
            # Add word boundaries to avoid partial matches
            pattern = r'\b' + pattern + r'\b'
            pattern_map[pattern] = standard_condition
    
    return pattern_map

def parse_title_for_condition(title: str) -> str:
    """
    Enhanced condition parsing that handles variations, typos, and case
    """
    if not title:
        return "Unknown"
    
    title_clean = title.lower().strip()
    pattern_map = create_condition_pattern_map()
    
    # Try to match each pattern
    for pattern, condition in pattern_map.items():
        if re.search(pattern, title_clean, re.IGNORECASE):
            return condition
    
    # Fallback: Check for common single letter abbreviations
    abbreviation_map = {
        r'\bnm\b': "Near Mint",
        r'\blp\b': "Lightly Played", 
        r'\bmp\b': "Moderately Played",
        r'\bhp\b': "Heavily Played",
        r'\bdmg\b': "Damaged",
        r'\bm\b': "Near Mint",  # Just "M" for mint
        r'\bd\b': "Damaged"     # Just "D" for damaged
    }
    
    for pattern, condition in abbreviation_map.items():
        if re.search(pattern, title_clean, re.IGNORECASE):
            return condition
    
    # Try to infer from other keywords
    inference_patterns = {
        r'perfect|pristine|flawless': "Near Mint",
        r'excellent|great\s*condition': "Near Mint", 
        r'good\s*condition|decent': "Lightly Played",
        r'played|used|worn': "Moderately Played",
        r'rough|beat\s*up|thrashed': "Heavily Played",
        r'torn|ripped|crease|bend': "Damaged"
    }
    
    for pattern, condition in inference_patterns.items():
        if re.search(pattern, title_clean, re.IGNORECASE):
            return condition
    
    return "Unknown"

def parsed_description_for_condition(description: str) -> str:
    """
    Parse the item description to determine condition, do not work because item query with itemId is required
    """
    if not description:
        return "Unknown"
    
    description_clean = description.lower().strip()
    pattern_map = create_condition_pattern_map()
    
    for pattern, condition in pattern_map.items():
        if re.search(pattern, description_clean, re.IGNORECASE):
            return condition
    
    return "Unknown"