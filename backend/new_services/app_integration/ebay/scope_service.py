#from backend.repositories.app_integration.scope_management   import register_scope
from typing import Optional


async def register_scope(repository, scope: str, scope_description : Optional[str]):
    return await repository.add(scope, scope_description)
