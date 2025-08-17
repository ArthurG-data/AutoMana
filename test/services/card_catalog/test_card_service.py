import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from uuid import UUID, uuid4

from backend.exceptions.card_catalogue import card_exception
from backend.new_services.card_catalog.card_service import (
    add,
    add_many,
    delete, 
    get, 
    get_many,
    get_all
)
from backend.schemas.card_catalog.card import CreateCard, CreateCards, BaseCard

@pytest.fixture
def mock_collection_repo():
    """Create a mock repository with AsyncMock methods"""
    repo = MagicMock()
    repo.get = AsyncMock()
    repo.get_many = AsyncMock()
    repo.add = AsyncMock()
    repo.add_many = AsyncMock()
    repo.update = AsyncMock()
    repo.delete = AsyncMock()
    repo.list = AsyncMock()
    return repo

@pytest.fixture
def test_card_data():
    """Create a test card with all required and optional fields"""
    return {
    # BaseCard fields
    "card_name": "Lightning Bolt",  # This is the alias in the JSON output
    "set_code": "M10",              # This is the alias in the JSON output
    "rarity_name": "Common",        # This is the alias in the JSON output
    "oracle_text": "Lightning Bolt deals 3 damage to any target.",
    "digital": False,
    
    # CreateCard fields
    "artist": "Christopher Rush",
    "artist_ids": ["550e8400-e29b-41d4-a716-446655440000"],
    "cmc": 1,
    "illustration_id": "00000000-0000-0000-0000-000000000001",
    "games": ["paper", "mtgo", "arena"],
    "mana_cost": "{R}",
    "collector_number": "147",
    "border_color": "black",
    "frame": "2015",
    "layout": "normal",
    "promo": False,  # From is_promo alias
    "keywords": ["Burn", "Direct Damage"],
    "type_line": "Instant",
    "oversized": False,
    "produced_mana": None,  # From color_produced alias
    "color_identity": ["R"],  # From card_color_identity alias
    "legalities": {
        "standard": "not_legal",
        "modern": "legal",
        "legacy": "legal",
        "commander": "legal"
    },
    "supertypes": [],
    "types": ["Instant"],
    "subtypes": [],
    "booster": True,
    "full_art": False,
    "flavor_text": "The spark of genius.",
    "textless": False,
    "power": None,
    "lang": "en",
    "promo_types": [],
    "toughness": None,
    "variation": False,
    "reserved": False,
    "card_faces": [],
    "set_name": "Magic 2010",
    "set": "M10",
    "set_id": "770e8400-e29b-41d4-a716-446655440002"
}

@pytest.fixture
def test_card_wrong_model():
    return CreateCard(
    # BaseCard fields
    card_name="Lightning Bolt Wrong Card",  # aliased to name
    set_code="M10",              # aliased to set
    rarity_name="Common",        # aliased to rarity
    oracle_text="Lightning Bolt deals 3 damage to any target.",
    digital=False,               # will be used by is_digital alias
    
    # CreateCard fields in exact order
    artist="Christopher Rush",
    artist_ids=[UUID("550e8400-e29b-41d4-a716-446655440000")],
    cmc=1,
    illustration_id=UUID("00000000-0000-0000-0000-000000000001"),
    games=["paper", "mtgo", "arena"],
    mana_cost="{R}",
    collector_number="147",
    border_color="black",
    frame="2015",
    layout="normal",

    keywords=["Burn", "Direct Damage"],
    type_line="Instant",
    oversized=False,
    produced_mana=None,          # aliased to color_produced
    color_identity=["R"],        # aliased to card_color_identity
    legalities={
        "standard": "not_legal",
        "modern": "legal",
        "legacy": "legal",
        "commander": "legal"
    },
    supertypes=[],
    types=["Instant"],           # Will be overwritten by validator
    subtypes=[],                 # Will be overwritten by validator
    promo=False,                 # Redundant but matches schema
    booster=True,
    full_art=False,
    flavor_text="The spark of genius.",
    textless=False,
    power=None,
    lang="en",
    promo_types=[],
    toughness=None,
    variation=False,
    reserved=False,
    card_faces=[],
    set_name="Magic 2010",
    set="M10",                   # Redundant with set_code but matches schema
    set_id=UUID("770e8400-e29b-41d4-a716-446655440002")
)

@pytest.fixture
def test_card_model():
    return CreateCard(
    # BaseCard fields
    card_name="Lightning Bolt",  # aliased to name
    set_code="M10",              # aliased to set
    rarity_name="Common",        # aliased to rarity
    oracle_text="Lightning Bolt deals 3 damage to any target.",
    digital=False,               # will be used by is_digital alias
    
    # CreateCard fields in exact order
    artist="Christopher Rush",
    artist_ids=[UUID("550e8400-e29b-41d4-a716-446655440000")],
    cmc=1,
    illustration_id=UUID("00000000-0000-0000-0000-000000000001"),
    games=["paper", "mtgo", "arena"],
    mana_cost="{R}",
    collector_number="147",
    border_color="black",
    frame="2015",
    layout="normal",

    keywords=["Burn", "Direct Damage"],
    type_line="Instant",
    oversized=False,
    produced_mana=None,          # aliased to color_produced
    color_identity=["R"],        # aliased to card_color_identity
    legalities={
        "standard": "not_legal",
        "modern": "legal",
        "legacy": "legal",
        "commander": "legal"
    },
    supertypes=[],
    types=["Instant"],           # Will be overwritten by validator
    subtypes=[],                 # Will be overwritten by validator
    promo=False,                 # Redundant but matches schema
    booster=True,
    full_art=False,
    flavor_text="The spark of genius.",
    textless=False,
    power=None,
    lang="en",
    promo_types=[],
    toughness=None,
    variation=False,
    reserved=False,
    card_faces=[],
    set_name="Magic 2010",
    set="M10",                   # Redundant with set_code but matches schema
    set_id=UUID("770e8400-e29b-41d4-a716-446655440002")
)

@pytest.mark.asyncio
async def test_add_card_success(mock_collection_repo, test_card_data, test_card_model):
    mock_collection_repo.add.return_value = test_card_data

    result = await add(mock_collection_repo, test_card_model)
    assert isinstance(result, BaseCard)

@pytest.mark.asyncio
async def test_add_card_failure(mock_collection_repo, test_card_model):
    mock_collection_repo.add.side_effect = Exception("Database error")

    with pytest.raises(Exception) as exc_info:
        await add(mock_collection_repo, test_card_model)
    
    assert str(exc_info.value) == "Failed to insert card: Database error"

@pytest.mark.asyncio
async def test_add_many_cards_success(mock_collection_repo, test_card_model):
    mock_collection_repo.add_many.return_value = {"inserted_count": 1}

    values_list = CreateCards(items=[test_card_model])
    result = await add_many(mock_collection_repo, values_list)
    
    assert result == 1
    mock_collection_repo.add_many.assert_called_once()

@pytest.mark.asyncio
async def test_add_many_cards_failure(mock_collection_repo, test_card_model):
    mock_collection_repo.add_many.side_effect = Exception("Database error")

    values_list = CreateCards(items=[test_card_model])
    
    with pytest.raises(Exception) as exc_info:
        await add_many(mock_collection_repo, values_list)
    
    assert str(exc_info.value) == "Failed to insert cards: Database error"

@pytest.mark.asyncio
async def test_delete_card_success(mock_collection_repo):
    card_id = uuid4()
    mock_collection_repo.delete.return_value = True
    output = await delete(mock_collection_repo, card_id)
    assert output == True
    mock_collection_repo.delete.assert_called_once_with(card_id)

@pytest.mark.asyncio
async def test_delete_card_id_not_found(mock_collection_repo):
    card_id = uuid4()
    mock_collection_repo.delete.return_value = False

    with pytest.raises(Exception) as exc_info:
        await delete(mock_collection_repo, card_id)
    assert str(exc_info.value) == f"Failed to delete card with ID {card_id}"

@pytest.mark.asyncio
async def test_delete_card_failure(mock_collection_repo):
    card_id = uuid4()
    mock_collection_repo.delete.side_effect = Exception("Database error")

    with pytest.raises(Exception) as exc_info:
        await delete(mock_collection_repo, card_id)
    
    assert str(exc_info.value) == "Failed to delete card: Database error"

@pytest.mark.asyncio
async def test_get_card_success(mock_collection_repo, test_card_model):
    card_id = UUID("550e8400-e29b-41d4-a716-446655440000")
    mock_collection_repo.get.return_value = test_card_model
    result = await get(mock_collection_repo, card_id)
    assert isinstance(result, BaseCard)
    assert result.name == "Lightning Bolt"

@pytest.mark.asyncio
async def test_get_card_not_found(mock_collection_repo):
    card_id = UUID("550e8400-e29b-41d4-a716-446655440000")
    mock_collection_repo.get.return_value = None

    with pytest.raises(Exception) as exc_info:
        await get(mock_collection_repo, card_id)
    
    assert str(exc_info.value) == f"Card with ID {card_id} not found"

@pytest.mark.asyncio
async def test_get_card_failure(mock_collection_repo):
    card_id = UUID("550e8400-e29b-41d4-a716-446655440000")
    mock_collection_repo.get.side_effect = Exception("Database error")

    with pytest.raises(Exception) as exc_info:
        await get(mock_collection_repo, card_id)
    
    assert str(exc_info.value) == "Failed to retrieve card: Database error"

@pytest.mark.asyncio
async def test_get_many_cards_success(mock_collection_repo, test_card_model):
    card_ids = [UUID("550e8400-e29b-41d4-a716-446655440000")]
    mock_collection_repo.list.return_value = [test_card_model]
    
    results = await get_many(mock_collection_repo, card_ids)
    assert len(results) == 1
    assert isinstance(results[0], BaseCard)
    assert results[0].name == "Lightning Bolt"

@pytest.mark.asyncio
async def test_get_many_cards_not_found(mock_collection_repo):
    card_ids = [UUID("550e8400-e29b-41d4-a716-446655440000")]
    mock_collection_repo.list.return_value = []

    with pytest.raises(Exception) as exc_info:
        await get_many(mock_collection_repo, card_ids)
    
    assert str(exc_info.value) == f"No cards found for IDs {card_ids}"

@pytest.mark.asyncio
async def test_get_many_cards_failure(mock_collection_repo):
    card_ids = [UUID("550e8400-e29b-41d4-a716-446655440000")]
    mock_collection_repo.list.side_effect = Exception("Database error")
    with pytest.raises(Exception) as exc_info:
        await get_many(mock_collection_repo, card_ids)
    
    assert str(exc_info.value) == "Failed to retrieve cards: Database error"

@pytest.mark.asyncio
async def test_get_all_cards_success(mock_collection_repo, test_card_model):
    mock_collection_repo.list.return_value = [test_card_model]
    
    results = await get_all(mock_collection_repo)
    assert len(results) == 1
    assert isinstance(results[0], BaseCard)
    assert results[0].name == "Lightning Bolt"

@pytest.mark.asyncio
async def test_get_all_cards_not_found(mock_collection_repo):
    mock_collection_repo.list.return_value = []

    with pytest.raises(card_exception.CardNotFoundError) as exc_info:
        await get_all(mock_collection_repo)
    
    assert str(exc_info.value) == "No cards found"

@pytest.mark.asyncio
async def test_get_all_cards_failure(mock_collection_repo): 
    mock_collection_repo.list.side_effect = card_exception.CardRetrievalError("Database error")

    with pytest.raises(card_exception.CardRetrievalError) as exc_info:
        await get_all(mock_collection_repo)
    
    assert str(exc_info.value) == "Failed to retrieve cards: Database error"

