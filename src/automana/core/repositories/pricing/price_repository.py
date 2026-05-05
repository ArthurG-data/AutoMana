from datetime import date
from typing import Optional
import logging

from automana.core.repositories.abstract_repositories.AbstractDBRepository import AbstractRepository

logger = logging.getLogger(__name__)


class PricingTierRepository(AbstractRepository):
    """Repository for pricing tier aggregation procedures."""

    def __init__(self, connection, executor=None):
        super().__init__(connection, executor)

    @property
    def name(self) -> str:
        return "PriceRepository"

    async def refresh_daily_prices(
        self,
        p_from: Optional[date] = None,
        p_to: Optional[date] = None,
    ) -> dict:
        """
        Populate Tier 2 (print_price_daily) from Tier 1 (price_observation).

        Links source_product_id → card_version_id via mtg_card_products.

        Args:
            p_from: Start date (inclusive). If None, uses last_processed_date from watermark.
            p_to: End date (inclusive). If None, uses CURRENT_DATE - 1.

        Returns:
            Dict with procedure output (notice messages, row counts).
        """
        try:
            await self.execute_procedure(
                "pricing.refresh_daily_prices",
                (p_from, p_to),
            )
            logger.info(
                "refresh_daily_prices completed",
                extra={"p_from": p_from, "p_to": p_to},
            )
            return {"status": "success"}
        except Exception as e:
            logger.error(
                "refresh_daily_prices failed",
                extra={"p_from": p_from, "p_to": p_to, "error": str(e)},
            )
            raise

    async def archive_to_weekly(
        self,
        older_than_interval: str = "5 YEARS",
    ) -> dict:
        """
        Archive Tier 2 (print_price_daily) rows to Tier 3 (print_price_weekly).

        Args:
            older_than_interval: PostgreSQL interval string (e.g., '5 YEARS', '90 DAYS').

        Returns:
            Dict with procedure output (notice messages, row counts).
        """
        try:
            # Convert string interval to proper SQL format
            interval_param = f"INTERVAL '{older_than_interval}'"
            await self.execute_procedure(
                "pricing.archive_to_weekly",
                (interval_param,),
            )
            logger.info(
                "archive_to_weekly completed",
                extra={"older_than_interval": older_than_interval},
            )
            return {"status": "success"}
        except Exception as e:
            logger.error(
                "archive_to_weekly failed",
                extra={"older_than_interval": older_than_interval, "error": str(e)},
            )
            raise

    async def execute_procedure(self, proc_name: str, args: tuple) -> None:
        """
        Execute a stored procedure with arguments.

        Args:
            proc_name: Fully qualified procedure name (e.g., 'pricing.refresh_daily_prices')
            args: Tuple of arguments to pass to the procedure
        """
        # Build the CALL statement
        placeholders = ", ".join(f"${i+1}" for i in range(len(args)))
        call_stmt = f"CALL {proc_name}({placeholders})"

        # Execute via the connection
        await self.connection.execute(call_stmt, *args)
