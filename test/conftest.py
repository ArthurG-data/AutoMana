# test/conftest.py
import pytest
import os
import asyncio
from dotenv import load_dotenv
from unittest.mock import patch, MagicMock, AsyncMock

# Load test environment variables
@pytest.fixture(scope="session", autouse=True)
def load_test_env():
    """Load test environment variables"""
    # Try loading from .env.test first, then fall back to .env
    env_loaded = load_dotenv(".env.test")
    if not env_loaded:
        load_dotenv(".env")
    
    # Set critical test variables if not already set
    if not os.getenv("POSTGRES_USER"):
        os.environ["POSTGRES_USER"] = "test_user"
    if not os.getenv("POSTGRES_PASSWORD"):
        os.environ["POSTGRES_PASSWORD"] = "test_password"
    if not os.getenv("POSTGRES_DB"):
        os.environ["POSTGRES_DB"] = "test_db"
    if not os.getenv("POSTGRES_HOST"):
        os.environ["POSTGRES_HOST"] = "localhost"
    if not os.getenv("ENCRYPT_ALGORITHM"):
        os.environ["ENCRYPT_ALGORITHM"] = "HS256"
    if not os.getenv("PGP_SECRET_KEY"):
        os.environ["PGP_SECRET_KEY"] = "test_pgp_key"

# Configure pytest for asyncio
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

# Mock DB settings
@pytest.fixture
def mock_db_settings():
    """Mock database settings"""
    mock_settings = MagicMock()
    mock_settings.postgres_host = "localhost"
    mock_settings.postgres_user = "test_user"
    mock_settings.postgres_password = "test_password"
    mock_settings.postgres_db = "test_db"
    return mock_settings

# Mock the get_db_settings function
@pytest.fixture
def mock_get_db_settings(mock_db_settings):
    """Mock the get_db_settings function"""
    with patch("backend.dependancies.settings.get_db_settings") as mock:
        mock.return_value = mock_db_settings
        yield mock

# Mock asyncpg pool
@pytest.fixture
async def mock_asyncpg_pool():
    """Create a mock asyncpg pool"""
    pool = AsyncMock()
    conn = AsyncMock()
    
    # Configure acquire to work both as async function and context manager
    async def mock_acquire():
        return conn
        
    # Make it work with async with
    cm = AsyncMock()
    cm.__aenter__.return_value = conn
    mock_acquire.__aenter__ = cm.__aenter__
    mock_acquire.__aexit__ = cm.__aexit__
    
    pool.acquire.return_value = mock_acquire()
    
    # Mock other methods
    pool.close = AsyncMock()
    
    return pool, conn

# Mock init_async_pool
@pytest.fixture
async def mock_init_pool(mock_asyncpg_pool):
    """Mock the init_async_pool function"""
    pool, _ = mock_asyncpg_pool
    with patch("backend.database.get_database.init_async_pool") as mock:
        mock.return_value = pool
        yield mock