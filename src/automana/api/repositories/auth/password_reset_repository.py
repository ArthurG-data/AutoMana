from uuid import UUID
from datetime import datetime
from automana.core.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository


class PasswordResetRepository(AbstractRepository):
    def __init__(self, connection, executor=None):
        super().__init__(connection, executor)

    @property
    def name(self) -> str:
        return "PasswordResetRepository"

    async def create(self, user_id: UUID, token_hash: str, expires_at: datetime) -> dict:
        query = """
        INSERT INTO user_management.password_reset_tokens (user_id, token_hash, expires_at)
        VALUES ($1, $2, $3)
        RETURNING *;
        """
        result = await self.execute_query(query, (user_id, token_hash, expires_at))
        return result[0] if result else None

    async def get_by_token_hash(self, token_hash: str) -> dict | None:
        query = """
        SELECT * FROM user_management.password_reset_tokens
        WHERE token_hash = $1;
        """
        result = await self.execute_query(query, (token_hash,))
        return result[0] if result else None

    async def mark_used(self, token_id: UUID) -> None:
        query = """
        UPDATE user_management.password_reset_tokens
        SET used_at = NOW()
        WHERE id = $1;
        """
        await self.execute_command(query, (token_id,))

    async def invalidate_for_user(self, user_id: UUID) -> None:
        query = """
        DELETE FROM user_management.password_reset_tokens
        WHERE user_id = $1 AND used_at IS NULL AND expires_at > NOW();
        """
        await self.execute_command(query, (user_id,))

    async def list(self):
        raise NotImplementedError
