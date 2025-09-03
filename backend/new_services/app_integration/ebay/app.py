from backend.schemas.external_marketplace.ebay.app import NewEbayApp, AssignScope
from uuid import UUID
from backend.exceptions.app_integration.ebay import app_exception
from backend.repositories.app_integration.ebay.app_repository import EbayAppRepository
from backend.schemas.settings import EbaySettings

async def register_app(repository: EbayAppRepository, NewApp : NewEbayApp) -> bool:
    """Register an eBay app with the provided settings."""
    try:
        input = (NewApp.app_id, NewApp.redirect_uri, NewApp.response_type, NewApp.secret)
        value = await repository.add(input)
        if not value:
            raise app_exception.EbayAppRegistrationException("Failed to register eBay app")
        return True
    except app_exception.EbayAppRegistrationException as e:
        raise app_exception.EbayAppRegistrationException(f"Failed to register eBay app: {str(e)}")
""" Probably not needed, ebay id is not required for the app registration.
def assign_app(repository: EbayAppRepository, app_id : UUID, ebay_id :str):
    repository.update({
        "app_id": app_id,
        "ebay_id": ebay_id
    })
"""

async def assign_scope(repository: EbayAppRepository, newScope: AssignScope) -> bool | None:
    """assign a scope to a user for an eBay app."""
    try:
        value = await repository.assign_scope(newScope.scope, newScope.app_id, newScope.user_id)
        if not value:
            raise app_exception.EbayScopeAssignmentException("Failed to assign scope to eBay app with ID: {}".format(newScope.app_id))
        return value
    except app_exception.EbayScopeAssignmentException:
        raise
    except app_exception.EbayScopeAssignmentException as e:
        raise app_exception.EbayScopeAssignmentException(f"Failed to assign scope to eBay app: {str(e)}")