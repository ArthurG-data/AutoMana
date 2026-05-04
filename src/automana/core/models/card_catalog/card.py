
from pydantic import ConfigDict, Field, field_validator, model_validator, BaseModel
from uuid import UUID
from typing import Any, Dict, Optional,  List, Union
from automana.core.utils.type_parser import process_type_line
from automana.core.utils.card_face_parser import parse_card_faces
from datetime import datetime
import json

class BaseCard(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    card_version_id: Optional[Union[UUID, str]] = Field(default=None, title="Unique card version identifier")
    name: str = Field(alias="card_name", title="The name of the card")
    set_name: str = Field(title="The complete name of the set")
    set: str = Field(alias="set_code", title="The abbreviation of the set")
    cmc: Union[int, float] = Field(title="Converted mana cost of the card")
    rarity: str = Field(alias="rarity_name", title="The rarity of the card")
    oracle_text: Optional[str] = Field(default="", title="The text on the card")
    digital: bool = Field(title="Is the card released only on digital platform")
    image_normal: Optional[str] = Field(default=None, title="URL to normal-sized card image from Scryfall")

    @staticmethod
    def to_json_safe(data):
        def clean(obj):
            if isinstance(obj, dict):
                return {k: clean(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [clean(v) for v in obj]
            elif isinstance(obj, UUID):
                return str(obj)
            else:
                return obj
        return json.dumps(clean(data))

class CardDetail(BaseCard):
    image_large: Optional[str] = Field(default=None, title="URL to large-sized card image from Scryfall")
    price_history_list_avg: Optional[List[float]] = Field(
        default=None,
        title="Daily list average prices in dollars for selected time range"
    )
    price_history_sold_avg: Optional[List[float]] = Field(
        default=None,
        title="Daily sold average prices in dollars for selected time range"
    )

class CardFace(BaseModel):
    name: str
    face_index : Optional[int] = 0
    mana_cost: Optional[str] = None
    type_line: Optional[str] = None
    oracle_text: Optional[str] = None
    power: Optional[Union[int, str]] = None
    toughness: Optional[Union[int, str]] = None
    flavor_text: Optional[str] = None
    artist: Optional[str] = None
    artist_id: Optional[UUID] = None
    illustration_id: Optional[UUID] = None
    supertypes: List[str] = []
    types: List[str] = []
    subtypes: List[str] = []
    loyalty: Optional[Union[int, str]] = None

    @model_validator(mode='after')
    def process_type_line(cls, values):
        if not values.type_line:
            return values
    
        parsed = process_type_line(values.type_line)
        values.types = parsed["types"]
        values.supertypes = parsed["supertypes"]
        values.subtypes = parsed["subtypes"]
        return values
    
    @field_validator("artist", mode="after")
    @classmethod
    def parse_artist(cls, v):
        if isinstance(v, str) and "&" in v:
            return [a.strip() for a in v.split("&")]
        return v

class CreateCard(BaseCard):
    artist: Union[str, list[str]]
    artist_ids : Union[UUID, List[UUID]] = []
    cmc : Union[int, float] = Field(default=0)
    illustration_id: Optional[UUID | list[UUID]] = UUID('00000000-0000-0000-0000-000000000001')
    games : List[str] = []
    mana_cost : Optional[str]=Field(max_length=100, default=None)
    collector_number: Union[int, str] 
    border_color: str = Field(max_length=20)
    frame: str = Field(max_length=20)
    layout: str = Field(max_length=20)
    is_promo: bool = Field(alias="promo")
    is_digital: bool = Field(alias="digital")
    keywords: Optional[List[str]]=[]
    type_line: Optional[str]=None
    image_uris : Optional[Dict[str,Any]]= None
    oversized : Optional[bool]=False
    color_produced: Optional[List[str]] = Field(alias="produced_mana", default=None)
    card_color_identity: List[str] = Field(alias="color_identity")
    legalities : dict
    supertypes: List[str] = []
    types: List[str] = []
    subtypes: List[str] = []
    promo : Optional[bool]=False
    booster : Optional[bool]=True
    full_art : Optional[bool]=False
    flavor_text : Optional[str] = None
    textless : Optional[bool]=False
    power : Optional[Union[int, str]] = None
    lang : Optional[str]='en'
    loyalty : Optional[Union[int, str]]=None
    promo_types : Optional[List[str]]=[]
    toughness : Optional[Union[int, str]]=None
    defense : Optional[Union[int, str]]=None
    variation : Optional[bool]=False
    reserved : bool=Field(default=False)
    card_faces : Optional[List[CardFace]]=[]
    set_name : str=Field('MISSING_SET')
    set : str
    set_id : UUID
    id: Optional[UUID]=None
    oracle_id: Optional[UUID]=None #should be the unique card id 
    multiverse_ids: Optional[List[int]]=[]
    tcgplayer_id: Optional[int]=None
    tcgplayer_etched_id: Optional[int]=None
    cardmarket_id: Optional[int]=None

    @field_validator("artist", mode="after")
    @classmethod
    def parse_artist(cls, v):
        if isinstance(v, str) and "&" in v:
            return [a.strip() for a in v.split("&")]
        return v

    def prepare_for_db(self):
        """
        Prepare the card for database insertion by converting types and ensuring all fields are set.
        """
        
        return (
        self.name,
        int(self.cmc) if self.cmc is not None else 0,
        self.mana_cost,
        self.reserved,
        self.oracle_text,
        self.set_name,
        str(self.collector_number),
        self.rarity,
        self.border_color,
        self.frame,
        self.layout,
        self.is_promo,
        self.is_digital,
        self.to_json_safe(self.keywords),
        self.to_json_safe(self.card_color_identity),        # p_colors
        self.to_json_safe(self.artist) if isinstance(self.artist, list) else json.dumps([self.artist]),
        self.to_json_safe(self.artist_ids) if isinstance(self.artist_ids, list) else json.dumps([self.artist_ids]),
        self.to_json_safe(self.legalities),
        self.illustration_id if self.illustration_id else UUID("00000000-0000-0000-0000-000000000001"),
        self.to_json_safe(self.types),
        self.to_json_safe(self.supertypes),
        self.to_json_safe(self.subtypes),
        self.to_json_safe(self.games),
        self.oversized,
        self.booster,
        self.full_art,
        self.textless,
        str(self.power) if self.power is not None else None,
        str(self.toughness) if self.toughness is not None else None,
        str(self.loyalty) if self.loyalty is not None else None,
        str(self.defense) if self.defense is not None else None,
        self.to_json_safe(self.promo_types) if isinstance(self.promo_types, list) else json.dumps([self.promo_types]),
        self.variation,
        self.to_json_safe([f.model_dump() for f in self.card_faces]) if self.card_faces else json.dumps([]),

        self.to_json_safe(self.image_uris) if self.image_uris else json.dumps({}),
        
        self.id,
        self.oracle_id,
        self.to_json_safe(self.multiverse_ids) if self.multiverse_ids else json.dumps([]),
        self.tcgplayer_id,
        self.tcgplayer_etched_id,
        self.cardmarket_id,
    )
    def model_dump_for_sql(self) -> Dict[str, Any]:
        """
        Use Pydantic's built-in serialization with custom transformations
        """
        # Get the standard model dump
        data = self.model_dump(
            by_alias=True,  # Use field aliases
            exclude_none=False,  # Keep None values for proper handling
            mode='json'  # JSON-serializable format
        )

        return {
            "card_name": data["card_name"],
            "cmc": int(data["cmc"]) if data["cmc"] is not None else 0,
            "mana_cost": data["mana_cost"],
            "reserved": data["reserved"],
            "oracle_text": data["oracle_text"] or "",

            "set_name": data["set_name"],
            "collector_number": str(data["collector_number"]),
            "rarity_name": data["rarity_name"],
            "border_color": data["border_color"],
            "frame_year": data["frame"],
            "layout_name": data["layout"],
            "is_promo": data["promo"],
            "is_digital": data["digital"],
            "keywords": data["keywords"],
            "colors": data["color_identity"],
            "artist": data["artist"] if isinstance(data["artist"], list) else [data["artist"]],
            "artist_ids":  data["artist_ids"] if data["artist_ids"] else ["00000000-0000-0000-0000-000000000000"],
            "legalities": data["legalities"],
            "illustration_id": data["illustration_id"] if data["illustration_id"] else ["00000000-0000-0000-0000-000000000001"],
            "types": data["types"],
            "supertypes": data["supertypes"],
            "subtypes": data["subtypes"],
            "games": data["games"],
            "oversized": data["oversized"] or False,
            "booster": data["booster"] if data["booster"] is not None else True,
            "full_art": data["full_art"] or False,
            "textless": data["textless"] or False,
            "power": str(data["power"]) if data["power"] is not None else None,
            "toughness": str(data["toughness"]) if data["toughness"] is not None else None,
            "loyalty": str(data["loyalty"]) if data["loyalty"] is not None else None,
            "defense": str(data["defense"]) if data["defense"] is not None else None,
            "promo_types": data["promo_types"] or [],
            "variation": data["variation"] or False,
            "card_faces": data["card_faces"] or [],

            "image_uris": data["image_uris"] or [],

            "scryfall_id": data["id"],  
            "oracle_id": data["oracle_id"],
            "multiverse_ids": data["multiverse_ids"] or [],
            "tcgplayer_id": data["tcgplayer_id"],
            "tcgplayer_etched_id": data["tcgplayer_etched_id"],
            "cardmarket_id": data["cardmarket_id"],
        }
   
    @model_validator(mode='before')
    @classmethod
    def parse_and_clean_card_faces(cls, values):
        faces = values.get("card_faces")

        if faces is None:
            values["card_faces"] = []
        else:
            # If faces is a dict -> call your parse_card_faces() function
            faces = parse_card_faces(faces)  # returns List[CardFace]

            # Now clean the list
            clean_faces = []
            for face in faces:
                if face is None:
                    continue
                if isinstance(face, CardFace):
                    clean_faces.append(face)
                elif isinstance(face, dict):
                    clean_faces.append(CardFace(**face))
                else:
                    raise ValueError(f"Invalid card_face entry: {face}")

            values["card_faces"] = clean_faces

        return values
    
    @model_validator(mode='after')
    def process_type_line(self):
        tl = getattr(self, "type_line", None)
        
        # For double-faced cards, get type_line from first face
        if (not tl) and self.card_faces:
            tl = self.card_faces[0].type_line
        
        if not tl:
            self.types, self.supertypes, self.subtypes = [], [], []
            return self
        
        # Handle double-faced cards: "type1 // type2" -> use only first face
        if '//' in tl:
            tl = tl.split('//')[0].strip()
        
        parsed = process_type_line(tl)
        
        # Filter out common words that aren't types
        stopwords = {'of', 'and', 'or', 'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'with'}
        
        self.types = [t for t in parsed.get("types", []) if t.lower() not in stopwords]
        self.supertypes = [t for t in parsed.get("supertypes", []) if t.lower() not in stopwords]
        self.subtypes = [t for t in parsed.get("subtypes", []) if t.lower() not in stopwords]
        
        return self
    

class CreateCards(BaseModel):
    items :List[CreateCard] = []

    def __iter__(self):
        return iter(self.items)
    def __len__(self):
        return len(self.items)
    def __getitem__(self, index):
        return self.items[index]    
    def __setitem__(self, index, value):
        self.items[index] = value
    def __delitem__(self, index):
        del self.items[index]
    
    def model_dump_for_db(self) -> List[Dict[str, Any]]:
        """
        Alternative: Use model_dump with custom serialization
        """
        return [card.model_dump_for_sql() for card in self.items]

    def prepare_for_db(self) -> str:
        card_data = self.model_dump_for_db()
        return json.dumps(card_data)

    def get_batch_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the batch for logging/debugging
        """
        if not self.items:
            return {"total_cards": 0, "sets": [], "rarities": []}
        
        sets = list(set(card.set_name for card in self.items))
        rarities = list(set(card.rarity for card in self.items))
        
        return {
            "total_cards": len(self.items),
            "sets": sets,
            "rarities": rarities,
            "sample_cards": [card.name for card in self.items[:3]]
        }


class CardSuggestion(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    card_version_id: UUID
    card_name: str
    set_code: str
    collector_number: str
    rarity_name: str
    scryfall_id: Optional[str] = None
    score: float


class CardSuggestionResponse(BaseModel):
    suggestions: list[CardSuggestion]


class CatalogStats(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_card_versions: int
    data_source: str
    last_updated: Optional[datetime] = None
