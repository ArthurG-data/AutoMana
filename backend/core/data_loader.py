import importlib
from typing import Iterable
import logging

logger = logging.getLogger(__name__)

def load_services(modules: Iterable[str]) -> None:
    try:
        for m in modules:
            importlib.import_module(m)
            logger.debug(f"Successfully loaded service module: {m}")
    except ImportError as e:
        raise RuntimeError(f"Error loading service modules: {e}") from e