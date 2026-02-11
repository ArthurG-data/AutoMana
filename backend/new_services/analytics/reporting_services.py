from backend.core.service_registry import ServiceRegistry
from backend.repositories.ops import ops_repository
from backend.repositories.analytics_repositories.analytics_repository import AnalyticsRepository

@ServiceRegistry.register(
        "analytics.daily_summary.generate_report",
        db_repositories=["analytics"]
)
async def daily_summary_report(analytics_repository: AnalyticsRepository) -> None:
    """for now, how many new sets and how many new cards were added in the last day"""
    result = await analytics_repository.generate_daily_summary_report()
    return result