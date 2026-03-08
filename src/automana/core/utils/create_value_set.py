
from typing import Optional

def create_value(values, is_list : bool, limit : Optional[int]=None, offset : Optional[int]=None):
    if is_list:
        values = ((values ), limit , offset)
    elif values:
        values = (values ,)
    else:
        values = (limit , offset)
    return values
