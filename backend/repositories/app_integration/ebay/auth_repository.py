from backend.repositories.AbstractRepository import AbstractRepository

class EbayAuthRepository(AbstractRepository):
    def __init__(self, connection, queryExecutor):
        super().__init__(queryExecutor)
        self.connection = connection
        self.queryExecutor = queryExecutor

    @property
    def name(self):
        return "EbayAuthRepository"
    async def get(self):
        raise NotImplementedError("This method is not implemented in EbayAuthRepository")
    async def get_many(self):
        raise NotImplementedError("This method is not implemented in EbayAuthRepository")
    async def create(self, data):
        raise NotImplementedError("This method is not implemented in EbayAuthRepository")
    async def update(self, data):
        raise NotImplementedError("This method is not implemented in EbayAuthRepository")   
    async def delete(self, data):
        raise NotImplementedError("This method is not implemented in EbayAuthRepository")   
