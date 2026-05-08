from typing import Optional

from automana.core.repositories.app_integration.ebay.auth_repository import EbayAuthRepository
from automana.core.service_registry import ServiceRegistry


async def register_scope(repository, scope: str, scope_description: Optional[str]):
    return await repository.add(scope, scope_description)


@ServiceRegistry.register(
    "integrations.ebay.get_scopes_by_environment",
    db_repositories=["auth"],
)
async def get_scopes_by_environment(
    auth_repository: EbayAuthRepository,
    ebay_environment: str,
) -> list[dict]:
    return await auth_repository.get_scopes_by_environment(ebay_environment)
