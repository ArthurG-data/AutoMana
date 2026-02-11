import importlib
from typing import Iterable
import logging

logger = logging.getLogger(__name__)

def load_services(modules: Iterable[str]) -> None:
    failed_modules = []
    for m in modules:
        try:
            importlib.import_module(m)
            logger.debug(f"Successfully loaded service module: {m}")
        except Exception as e:
            logger.error(f"Failed to load service module '{m}': {type(e).__name__}: {e}")
            failed_modules.append((m, e))
    
    if failed_modules:
        error_msg = "\n".join([f"  - {m}: {e}" for m, e in failed_modules])
        raise RuntimeError(f"Failed to load {len(failed_modules)} service module(s):\n{error_msg}")