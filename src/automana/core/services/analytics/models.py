from dataclasses import dataclass
from typing import Optional


@dataclass
class PricingResult:
    price: float
    description: str
    expected_speed: str
    profit_margin: str
    confidence: float = 0.0
    metadata: Optional[dict] = None
