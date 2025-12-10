from abc import ABC, abstractmethod
from typing import Dict, Optional
from backend.new_services.analysis.pricing import PricingResult

class PricingStrategy(ABC):
    """Abstract base class for pricing strategies"""
    def __init__(self, name:str, description: Optional[str] = ""):
        self.name = name
        self.description = description

    @abstractmethod
    def calculate_price(self,
                        stats : Dict,
                        percentiles : Dict,
                        markest_data: Dict = None
                        ) -> PricingResult:
        pass

    @abstractmethod
    def is_suitable(self, market_conditions: Dict) -> bool:
        """Determine if this strategy is suitable for current market conditions"""
        pass

class QuickSaleStrategy(PricingStrategy):
    def __init__(self):
        super().__init__("Quick Sale Strategy", "A strategy focused on quick sales at lower margins.")

    def calculate_price(self,
                        stats: Dict,
                        percentiles: Dict,
                        market_data: Dict = None
                        ) -> PricingResult:
        # Implementation for quick sale strategy
        base_price = percentiles['p25']  # Targeting the 25th percentile for quick sales

        if market_data and market_data.get('volatility', 0) > 0.3:
            price = base_price * 0.95  # Reduce price by 5% in high volatility markets
            confidence = 0.9
        else:
            price = base_price
            confidence = 0.85
        return PricingResult(
            price=round(price, 2),
            description='Price in bottom 25% for quick sale',
            expected_speed='Very Fast (1-3 days)',
            profit_margin="Low",
            confidence=confidence,
            metadata={'percentile_used': 'p25', 'volatility_adjustment': market_data.get('volatility', 0) if market_data else 0}
        )
    def is_suitable(self, market_conditions: Dict) -> bool:
        """Determine if this strategy is suitable based on market conditions"""
        return (
             market_conditions.get('inventory_level', 'medium') == 'high' or
            market_conditions.get('cash_flow_priority', False) or
            market_conditions.get('volatility', 0) > 0.3
        )
    
class CompetitiveStrategy(PricingStrategy):
    def __init__(self):
        super().__init__("Competitive", "Price slightly below market for good balance")
    
    def calculate_price(self, stats: Dict, percentiles: Dict, market_data: Dict = None) -> PricingResult:
        base_price = stats['median_price']
        
        # Adjust based on competition
        competition_level = market_data.get('competition_level', 'medium') if market_data else 'medium'
        
        if competition_level == 'high':
            price = base_price * 0.92  # More aggressive discount
            confidence = 0.8
        elif competition_level == 'low':
            price = base_price * 0.98  # Less discount
            confidence = 0.9
        else:
            price = base_price * 0.95  # Standard discount
            confidence = 0.85
        
        return PricingResult(
            price=price,
            description=f'Priced at {((price/base_price - 1) * 100):+.1f}% vs median for competitive positioning',
            expected_speed='Fast (3-7 days)',
            profit_margin='Medium',
            confidence=confidence,
            metadata={'competition_adjustment': competition_level, 'median_price': base_price}
        )
    
    def is_suitable(self, market_conditions: Dict) -> bool:
        # Good general-purpose strategy
        return True

class PremiumStrategy(PricingStrategy):
    def __init__(self):
        super().__init__("Premium", "Price high for maximum profit")
    
    def calculate_price(self, stats: Dict, percentiles: Dict, market_data: Dict = None) -> PricingResult:
        base_price = percentiles['p75']
        
        # Only suitable in certain conditions
        card_rarity = market_data.get('card_rarity', 'common') if market_data else 'common'
        seller_reputation = market_data.get('seller_reputation', 'average') if market_data else 'average'
        
        # Premium pricing adjustments
        if card_rarity in ['mythic', 'rare'] and seller_reputation == 'high':
            price = base_price * 1.05  # Premium bump
            confidence = 0.75
        else:
            price = base_price
            confidence = 0.6
        
        return PricingResult(
            price=price,
            description='Premium pricing (top 25%)',
            expected_speed='Slow (2-4 weeks)',
            profit_margin='High',
            confidence=confidence,
            metadata={'rarity_bonus': card_rarity in ['mythic', 'rare'], 'reputation_bonus': seller_reputation == 'high'}
        )
    
    def is_suitable(self, market_conditions: Dict) -> bool:
        # Only suitable for rare cards, good seller reputation, stable market
        return (
            market_conditions.get('card_rarity') in ['mythic', 'rare'] and
            market_conditions.get('seller_reputation', 'average') in ['high', 'excellent'] and
            market_conditions.get('volatility', 0) < 0.2
        )
    
class PricingStrategyManager:
    def __init__(self, strategies: Dict[str, PricingStrategy]):
        self.strategies = strategies 
    
    def get_all_strategies(self, stats: Dict, percentiles: Dict, market_data: Dict = None) -> Dict[str, PricingResult]:
        """Get results from all strategies"""
        return {
            name: strategy.calculate_price(stats, percentiles, market_data)
            for name, strategy in self.strategies.items()
        }
    
    def get_suitable_strategies(self, market_conditions: Dict, stats: Dict, percentiles: Dict) -> Dict[str, PricingResult]:
        """Get only strategies suitable for current conditions"""
        suitable = {}
        for name, strategy in self.strategies.items():
            if strategy.is_suitable(market_conditions):
                suitable[name] = strategy.calculate_price(stats, percentiles, market_conditions)
        return suitable
    
    def recommend_strategy(self, market_conditions: Dict, stats: Dict, percentiles: Dict) -> tuple[str, PricingResult]:
        """Recommend the best strategy based on conditions"""
        suitable = self.get_suitable_strategies(market_conditions, stats, percentiles)
        
        if not suitable:
            # Fallback to competitive
            return 'competitive', self.strategies['competitive'].calculate_price(stats, percentiles, market_conditions)
        
        # Choose highest confidence strategy
        best_strategy = max(suitable.items(), key=lambda x: x[1].confidence)
        return best_strategy
