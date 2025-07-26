from backend.repositories.AbstractRepository import AbstractRepository

class AuthRepository(AbstractRepository):
    def __init__(self, connection, queryexecutor):
        super().__init__(connection, queryexecutor)

    @property
    def table_name(self) -> str:
        return "authRepository"
    
    
     