from pydantic import BaseModel, model_validator
from typing import Optional, List


class Theme(BaseModel):
    code : str
    name : str

    @model_validator(mode='after')
    def validate_code_and_name(self):
        if len(self.code) < 3:
            raise ValueError("Theme code must be at least 3 characters long.")
        if len(self.name) <1:
            raise ValueError("Theme name must not be empty.")

class ThemeWithId(Theme):
    theme_id : int

class DeleteTheme(BaseModel):
    code : str

class InsertTheme(Theme):
    pass

class UpdateTheme(BaseModel):
    theme_id : int
    code : Optional[str] = None
    name : Optional[str] = None

    @model_validator(mode='after')
    def validate_code_and_name(self):
        if len(self.code) < 3:
            raise ValueError("Theme code must be at least 3 characters long.")
        if len(self.name) <1:
            raise ValueError("Theme name must not be empty.")

class ThemeList(BaseModel):
    items: List[ThemeWithId]
    count: int
    page: Optional[int] = 1
    pages: Optional[int] = 1
    limit: Optional[int] = None