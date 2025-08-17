from backend.repositories.AbstractRepository import AbstractRepository

class EbayInventoryRepository(AbstractRepository):
    def __init__(self, queryExecutor):
        super().__init__(queryExecutor)
    
    @property
    def name(self):
        return "EbayInventoryRepository"
    
    async def get(self):
        """
        Fetches the inventory data from the eBay API.
        This method should be implemented to interact with the eBay API.
        """
        raise NotImplementedError("This method should be implemented in a subclass.")
    async def add(self, data):
        """
        Adds new inventory data to the eBay API.
        This method should be implemented to interact with the eBay API.
        """
        raise NotImplementedError("This method should be implemented in a subclass.")
    async def update(self, data):
        """
        Updates existing inventory data in the eBay API.
        This method should be implemented to interact with the eBay API.
        """
        raise NotImplementedError("This method should be implemented in a subclass.")

    async def delete(self, item_id):
        """
        Deletes an item from the eBay inventory.
        This method should be implemented to interact with the eBay API.
        """
        raise NotImplementedError("This method should be implemented in a subclass.")