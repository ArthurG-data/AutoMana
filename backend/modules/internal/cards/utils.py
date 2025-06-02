
def process_type_line(card_type_line : str):
    super_types = {'Basic', 'Elite','Host', 'Legendary', 'Ongoing', 'Snow', 'World'}
    obsolet_map = {'Continuous Artifact' : 'Artifact','Interrupt' : 'Instant','Local enchantment' : 'Enchantment','Mana source':'Instant', 'Mono Artifact' : 'Artifact', 'Poly Artifact' : 'Artifact', 'Summon' : 'Creature'}
    CARD_TYPES = {
    "Artifact", "Creature", "Enchantment", "Instant", "Land", "Planeswalker",
    "Sorcery", "Kindred", "Dungeon", "Battle", "Plane", "Phenomenon", 
    "Vanguard", "Scheme", "Conspiracy"
    }
    supertypes = []
    types = []
    subtypes = []
    # check for double faced cards

    if "—" in card_type_line:
        main_part, sub_part = map(str.strip, card_type_line.split("—", 1))
        subtypes = sub_part.split()
    else:
        main_part = card_type_line

    for part in main_part.split():
        if part in super_types:
            supertypes.append(part)
        elif part in CARD_TYPES:
            types.append(part)
        elif part in obsolet_map:
            # Convert legacy types (e.g., Summon → Creature)
            types.append(obsolet_map[part])
        else:
            # If no clear mapping, assume it's an old or custom subtype
            subtypes.append(card_type_line)

    return {
        "supertypes": supertypes,
        "types": types,
        "subtypes": subtypes
    }