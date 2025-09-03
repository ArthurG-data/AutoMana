from backend.repositories.AbstractRepository import AbstractRepository

class EbayListingRepository(AbstractRepository):
    def __init__(self, connection, queryExecutor):
        super().__init__(queryExecutor)
        self.connection = connection

    @property
    def name(self):
        return "EbayListingRepository"

    async def get(self):
        raise NotImplementedError("This method is not implemented in EbayListingRepository")

    async def get_many(self):
        raise NotImplementedError("This method is not implemented in EbayListingRepository")

    async def create(self, data):
        raise NotImplementedError("This method is not implemented in EbayListingRepository")

    async def update(self, data):
        raise NotImplementedError("This method is not implemented in EbayListingRepository")

    async def delete(self, data):
        raise NotImplementedError("This method is not implemented in EbayListingRepository")
