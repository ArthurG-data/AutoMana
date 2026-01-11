from backend.repositories.abstract_repositories.AbstractDBRepository import AbstractDBRepository



class MtgjsonRepository(AbstractDBRepository):
    def __init__(self, settings)  :
        super().__init__( settings)

        

    def name(self) -> str:
        return "MtgjsonRepository"
    
    async def copy_staged_card_data(self, filepath) -> None:
        
        await self.execute("TRUNCATE TABLE mtgjson_card_data")
        query = """
        COPY mtgjson_card_data FROM $1 WITH (FORMAT parquet, PARQUET_COMPRESSION 'SNAPPY')
        """
        await self.execute(query, filepath)