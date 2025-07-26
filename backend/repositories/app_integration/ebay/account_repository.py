
from backend.repositories.AbstractRepository import AbstractRepository

class EbayAccountRepository(AbstractRepository):
    def __init__(self, connection, queryExecutor):
        super().__init__(queryExecutor)
        self.connection = connection
  
    @property
    def name(self):
        return "EbayAccountRepository"

    def get(self):
        raise NotImplementedError("Method 'get' is not implemented in EbayAccountRepository")
    def get_many(self):
        raise NotImplementedError("Method 'get_many' is not implemented in EbayAccountRepository")
    def create(self, values):
        raise NotImplementedError("Method 'create' is not implemented in EbayAccountRepository")    
    def update(self, values):
        raise NotImplementedError("Method 'update' is not implemented in EbayAccountRepository")    
    def delete(self, values):
        raise NotImplementedError("Method 'delete' is not implemented in EbayAccountRepository")