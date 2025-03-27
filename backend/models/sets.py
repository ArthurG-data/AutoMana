from pydantic import BaseModel, Field
import datetime

class BaseSet(BaseModel):
  
    set_name : str=Field(
        title='The complete name of the set'
    )
    set_code : str =Field(
        title='The set symbols'
    )


class SetInDB(BaseSet):
    set_id : str=Field(
    title='The id in the database'
)
    set_type : str = Field(
    title='The type of set'
)

  
    digital : bool = Field(
        title='Is the set a digital only release'
)

    released_at : datetime.date = Field(
        tile = 'The released date of the set'
)

class SetwCount(SetInDB):
    card_count : int= Field(
        title='The number of card per sets'
    )