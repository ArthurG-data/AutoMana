from backend.core.settings import Settings, get_settings
import re

def assert_safe_database_url():
    settings = get_settings()
    if settings.env == "prod":
        # Example: enforce hostname or db name pattern
        if settings.DATABASE_NAME_EXPECTED and not re.search(
            rf"/{re.escape(settings.DATABASE_NAME_EXPECTED)}(\?|$)",
            settings.DATABASE_URL
        ):
            raise RuntimeError("Refusing to boot: DATABASE_URL is not the expected PROD DB.")