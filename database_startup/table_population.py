import datetime, json
from uuid import UUID, uuid4
from datetime import datetime
from typing import  List
from pydantic import BaseModel, field_validator
from collections import defaultdict

class UniqueSet(BaseModel):
    id: str  # ✅ Generates a unique UUID
    name: str
    code: str
    set_type: str
    released_at: datetime
    digital: bool
    parent_set_code: str | int | None=None
    nonfoil_only : bool
    foil_only : bool
    icon_svg_uri : str | int
        
    @field_validator("icon_svg_uri", mode="before")
    @classmethod
    def extract_icon_query(cls, value:str)-> str:
        """Extract query string after '?' in the URL and store it in `icon_query`."""
        parsed_url = value.split('/')[-1]
        return parsed_url  # Extracts only query parameters
# from the json file, add

                



def load_data(filename : str)->List[dict]:
    with open(filename,'r' ,encoding='utf-8') as file:
        data = json.load(file).get('data')
        return data
    
def get_or_add_index(mapping, key, counter)->int:
    """Retrieves index for a key, adding it if not present."""
    if key not in mapping:
        mapping[key] = counter
        return counter + 1
    return counter

def prepare_data(data :List)->dict:
    sets = []
    set_type_map = defaultdict(set)
    icon_map, set_map = defaultdict(set),defaultdict(set)
    foil_map = {0 : 'nonfoil_only',1 : 'foil_only',2: 'foil_and_nonfoil'}
    set_counter = 0
    icon_counter = 0

    for d in data:
        s =  UniqueSet(**d)
        
        set_counter = get_or_add_index(set_type_map, s.set_type, set_counter)
        icon_counter = get_or_add_index(icon_map, s.icon_svg_uri, icon_counter)
        foil_status =2
        if s.nonfoil_only:
            foil_status=0
        elif s.foil_only:
            foil_status=1
        set_map[s.code] = s.id
        sets.append((s.id, s.name, s.code, set_type_map[s.set_type], s.released_at, s.parent_set_code,s.digital,  foil_status, icon_map[s.icon_svg_uri]))
    set_map_data = [(value, key) for key, value in set_type_map.items()]
    foil_map = [(key, value) for key, value in foil_map.items()]
    icon_map = [(value, key) for key, value in icon_map.items()]
    
   
    for i, s in enumerate(sets):
        s_list = list(s)  # ✅ Convert tuple to list
        s_list[5] = set_map.get(s_list[5], None)  # ✅ Update value
        sets[i] = tuple(s_list)
      
    
    
    return {'sets' : sets, 'set_map' : set_map_data, 'set_map_data' : icon_map, 'foil_status' : foil_map} 

def populate_set(conn) -> dict:
    data = load_data('database_startup/files/sets.json')
    table_data = prepare_data(data)
    cursor = conn.cursor()
  
    try:
        cursor.executemany('INSERT INTO set_type_list_ref (set_type_id, set_type) VALUES(%s, %s)', table_data.get('set_map'))
        cursor.executemany('INSERT INTO foil_status_ref (foil_status_id, foil_status_desc) VALUES(%s, %s)', table_data.get('foil_status'))
        cursor.executemany('INSERT INTO icon_query_ref (icon_query_id, icon_quey) VALUES(%s, %s)', table_data.get('set_map_data'))
        cursor.executemany('INSERT INTO sets (set_id, set_name, set_code, set_type_id, released_at, parent_set,  digital , foil_status_id, icon_query_id) VALUES(%s,%s, %s, %s, %s,%s, %s, %s,%s)', table_data.get('sets'))
        conn.commit()
    except Exception as e:
        print('error:', e)
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def process_type_line(card):
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

    if "—" in card:
        main_part, sub_part = map(str.strip, card.split("—", 1))
        subtypes = sub_part.split()
    else:
        main_part = card

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
            subtypes.append(card)

    return {
        "supertypes": supertypes,
        "types": types,
        "subtypes": subtypes
    }
  
def prepare_cards(data, conn):
    unique_cards, keyword_card_table, color_card_table, color_produced_table = [], [], [], []
    game_table, artists_table, illustrations_table, card_legality_table, type_card_table, card_version = [], [], [], [], [], []

    keyword_map, color_map, artist_map, format_map, legality_map = defaultdict(set), defaultdict(set), defaultdict(set), defaultdict(set), defaultdict(set)
    rarity_map, layout_map, frame_map, border_map, unique_map = defaultdict(set), defaultdict(set), defaultdict(set), defaultdict(set), defaultdict(set)

    keyword_index = color_index = format_index = 0
    legal_index = rarity_index = layout_index = frame_index = border_index = 0

    cursor = conn.cursor()
    cursor.execute("SELECT set_id, set_code FROM sets")
    sets = cursor.fetchall()
    set_map = {set_[1]:set_[0] for set_ in sets}

    
    def get_or_add_index(mapping, key, counter):
        """Retrieves index for a key, adding it if not present."""
        if key not in mapping:
            mapping[key] = counter
            return counter + 1
        return counter

    for card in data:
        try:
            card_name = card.get('name', None)
            unique_card_index = unique_map.get(card_name, None)
            card_id = card.get('id', None)
            artist = card.get('artist')

            if not unique_card_index:
                unique_card_index = str(uuid4())
                unique_map[card_name] = unique_card_index
                card_cmc = card.get('cmc', 0)
                mana_cost = card.get('mana_cost', None)
                reserved = card.get('reserved', False)
            
                unique_cards.append((unique_card_index, card_name, card_cmc, mana_cost, reserved))
        

        # Process keywords
                for keyword in card.get('keywords', []):
                    keyword_index = get_or_add_index(keyword_map, keyword, keyword_index)
                    keyword_card_table.append((unique_card_index, keyword_map[keyword]))

            # Process colors
                for color in card.get('color_identity', []):
                    color_index = get_or_add_index(color_map, color, color_index)
                    color_card_table.append((unique_card_index, color_map[color]))

        # Process colors produced
                for color in card.get('produced_mana', []):
                    color_index = get_or_add_index(color_map, color, color_index)
                    color_produced_table.append((unique_card_index, color_map[color]))
                    
                for format_name, legality in card.get('legalities', {}).items():
                    format_index = get_or_add_index(format_map, format_name, format_index)
                    legal_index = get_or_add_index(legality_map, legality, legal_index)
                    card_legality_table.append((unique_card_index, format_map[format_name], legality_map[legality]))


        
            if artist:
                if not artist_map.get(artist, None):
                    artist_map.setdefault(artist, str(uuid4()))
                    artists_table.append((artist_map[artist], artist))
                
          

            type_dict = defaultdict(set)  # Use set to avoid duplicate entries
            faces = card.get('card_faces', None)
            # Process type lines for both faces
            if not faces:
                illustration_id = card.get('illustration_id', None)
                type_line = card.get('type_line', None)
                artist = card.get('artist', None)
                if artist and illustration_id:
                    if not artist_map.get(artist, None):
                        artist_map.setdefault(artist, str(uuid4()))
                        artists_table.append((artist_map[artist], artist))
                    illustrations_table.append((card_id, illustration_id, artist_map[artist]))
                if type_line:
                    types_dict = process_type_line(type_line)
                    for k, v in types_dict.items():
                        type_dict[k].update(v)
        
            else:

                for face in faces:
                    type_line = face.get('type_line', None)
                    illustration_id = face.get('illustration_id', None)
                    artist = face.get('artist', None)
                    if artist and illustration_id:
                        if not artist_map.get(artist, None):
                            artist_map.setdefault(artist, str(uuid4()))
                            artists_table.append((artist_map[artist], artist))

                        illustrations_table.append((card_id, illustration_id, artist_map[artist]))

                    if type_line:
                        types_dict = process_type_line(type_line)
                        for k, v in types_dict.items():
                            type_dict[k].update(v)  # Merge instead of overwriting
                
            # Process main type line if present (not a double-faced card)
            
            # Insert into type_card_table
            for k, v in type_dict.items():
                for entry in v:
                    if entry:
                        type_card_table.append((unique_card_index, k, entry))

        
            rarity_index = get_or_add_index(rarity_map, card.get('rarity'), rarity_index)
            frame_index = get_or_add_index(frame_map, card.get('frame'), frame_index)
            layout_index = get_or_add_index(layout_map, card.get('layout'), layout_index)            
            border_index = get_or_add_index(border_map, card.get('border_color'), border_index) 


            oracle_text = card.get('oracle_text', None)

            card_back_id = card.get('card_back_id', None)

            set_id = set_map.get(card.get('set', None), None)
            is_promo = card.get('promo', False)
            card_version.append((card_id,
                                unique_card_index,
                                card.get('oracle_text'),
                                set_id,
                                rarity_map.get(card.get('rarity')),
                                card.get('collector_number'),
                                border_map.get(card.get('border_color')),
                                frame_map.get(card.get('frame')),
                                layout_map.get(card.get('layout')),
                                is_promo,
                                card.get('digital')))
        
        except Exception as e:
            print("Error at index:", card_id, e)
    return {'unique_cards' : unique_cards, 'card_versions' : card_version,
                'keywords_ref' : keyword_map,'illustration_ref' : illustrations_table, 'legal_ref': legality_map,
                'legalities' : card_legality_table, 'format_ref':format_map, 'color_ref' : color_map, 'color_produced' : color_produced_table,
                'color_identity': color_card_table,'card_keywords' : keyword_card_table, 'layout_ref' : layout_map, 'frame_ref': frame_map,
                    'artist_ref': artist_map, 'rarity_ref': rarity_map, 'card_types': type_card_table, 'border_color_ref' : border_map}
            
def populate_cards(conn):
    with open('database_startup/files/default-cards-20250322090901.json','r' ,encoding='utf-8') as file:
        data = json.load(file)
    table_data = prepare_cards(data)
    cursor = conn.cursor()
    try:
        cursor.executemany("INSERT INTO unique_cards_ref ( unique_card_id, card_name, cmc, mana_cost, reserved) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (card_name) DO NOTHING" , table_data.get('unique_cards'))
        cursor.executemany("INSERT INTO border_color_ref ( border_color_id, border_color_name ) VALUES (%s, %s)" , [(v,k) for k,v in table_data.get('border_color_ref').items()] )
        cursor.executemany("INSERT INTO keywords_ref( keyword_id, keyword_name) VALUES (%s, %s)" , [(v,k) for k,v in table_data.get('keywords_ref').items()])
        cursor.executemany("INSERT INTO rarities_ref ( rarity_id, rarity_name) VALUES (%s, %s)" , [(v,k) for k,v in table_data.get('rarity_ref').items()])
        cursor.executemany("INSERT INTO colors_ref ( color_id, color_name ) VALUES (%s, %s)" , [(v,k) for k,v in table_data.get('color_ref').items()] )
        cursor.executemany("INSERT INTO card_keyword ( unique_card_id, keyword_id) VALUES (%s, %s) ON CONFLICT (unique_card_id, keyword_id) DO NOTHING" , table_data.get('card_keywords') )
        cursor.executemany("INSERT INTO color_produced ( unique_card_id, color_id) VALUES (%s, %s)" , table_data.get('color_produced') )
        cursor.executemany("INSERT INTO card_color_identity ( unique_card_id, color_id) VALUES (%s, %s)" ,table_data.get('color_identity')  )
        cursor.executemany("INSERT INTO legal_status_ref (legality_id, legal_status) VALUES (%s, %s)" ,[(v,k) for k,v in table_data.get('legal_ref').items()] )
        cursor.executemany("INSERT INTO formats_ref ( format_id, format_name ) VALUES (%s, %s)" ,  [(v,k) for k,v in table_data.get('format_ref').items()])
        cursor.executemany("INSERT INTO legalities ( unique_card_id, format_id, legality_id) VALUES (%s, %s, %s)" ,table_data.get('legalities')  )
        cursor.executemany("INSERT INTO frames_ref ( frame_id, frame_year ) VALUES (%s, %s)" ,  [(v,k) for k,v in table_data.get('frame_ref').items()])
        cursor.executemany("INSERT INTO layouts_ref ( layout_id, layout_name ) VALUES (%s, %s)" ,  [(v,k) for k,v in table_data.get('layout_ref').items()])
        cursor.executemany("INSERT INTO artists_ref ( artist_id, artist_name ) VALUES (%s, %s)" ,  [(v,k) for k,v in table_data.get('artist_ref').items()])

        cursor.executemany("INSERT INTO card_version ( card_version_id, unique_card_id,  oracle_text, set_id, rarity_id,collector_number,border_color_id,frame_id,layout_id, is_promo, is_digital ) VALUES (%s,%s, %s, %s, %s,%s, %s, %s,%s,%s, %s)" , table_data.get('card_versions') )
        cursor.executemany("INSERT INTO illustrations( card_version_id, illustration_id, artist_id ) VALUES (%s,%s, %s) ON CONFLICT ( illustration_id) DO NOTHING" , table_data.get('illustration_ref'))
        conn.commit()
    except Exception as e:
            print('error:', e)
            conn.rollback()
    finally:
            cursor.close()
            conn.close()
    

