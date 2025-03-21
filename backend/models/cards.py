from pydantic import BaseModel, Field
import datetime

class BaseCard(BaseModel):
    card_name : str =Field(
        title="The name of the card"
    )
    set_name : str = Field(
        title='The complete name of the set'
    )
    set_code : str = Field(
        title='The abbreviation of the set'
    )
    cmc: int = Field(
        title='The converted mana cost'
    )
    rarity_name : str = Field(
        title='The rarity of the card'
    )
    oracle_text : str = Field(
        title='The  text on the card'
    )

    released_at : datetime.date = Field(
        title='The data the card was released'
    )
    digital : bool = Field(
        title='Is the set a released only on digital plateform'
    )


