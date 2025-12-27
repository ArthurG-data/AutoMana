from backend.core.settings import Settings
import re

def assert_safe_database_url(settings: Settings) -> None:
    if settings.env == "prod":
        # Example: enforce hostname or db name pattern
        if settings.DATABASE_NAME_EXPECTED and not re.search(
            rf"/{re.escape(settings.DATABASE_NAME_EXPECTED)}(\?|$)",
            settings.DATABASE_URL_ASYNC
        ):
            raise RuntimeError("Refusing to boot: DATABASE_URL is not the expected PROD DB.")