import backend.repositories.AbstractRepository

class EbayOrderRepository(backend.repositories.AbstractRepository):
    def __init__(self, connection, queryExecutor):
        super().__init__(queryExecutor)
        self.connection = connection

    @property
    def name(self):
        return "EbayOrderRepository"

    async def get(self):
        raise NotImplementedError("This method is not implemented in EbayOrderRepository")

    async def get_many(self):
        raise NotImplementedError("This method is not implemented in EbayOrderRepository")

    async def create(self, data):
        raise NotImplementedError("This method is not implemented in EbayOrderRepository")

    async def update(self, data):
        raise NotImplementedError("This method is not implemented in EbayOrderRepository")

    async def delete(self, data):
        raise NotImplementedError("This method is not implemented in EbayOrderRepository")
