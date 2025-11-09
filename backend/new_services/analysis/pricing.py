from typing import Optional, Dict
from dataclasses import dataclass
from backend.new_services.analysis.strategies import PricingStrategy, PricingStrategyManager
from backend.new_services.analysis.utils import parse_title_for_condition, parsed_description_for_condition
import numpy as np
import statistics

@dataclass
class PricingResult:
    price : float
    description: float
    expected_speed : str
    profit_margin : str
    confidence: float =0.0
    metadata: Optional[dict] = None


def enhanced_pricing_analysis(ebay_result,  strategies: Dict[str, PricingStrategy], market_conditions: Dict = None):
    """Enhanced analysis using Strategy pattern"""
    
    # Your existing analysis logic...
    analysis = analyze_pricing_strategy(ebay_result)
    if 'error' in analysis:
        return analysis
    
    # Default market conditions
    if market_conditions is None:
        market_conditions = {
            'volatility': analysis['statistics']['std_deviation'] / analysis['statistics']['mean_price'],
            'competition_level': 'high' if analysis['statistics']['total_listings'] > 20 else 'medium',
            'inventory_level': 'medium',
            'cash_flow_priority': False,
            'card_rarity': 'rare',  # Would come from card database
            'seller_reputation': 'high'
        }
    
    # Use strategy manager
    strategy_manager = PricingStrategyManager(strategies)
                                            
    
    # Get all strategies
    all_strategies = strategy_manager.get_all_strategies(
        analysis['statistics'], 
        analysis['percentiles'], 
        market_conditions
    )
    
    # Get recommendation
    recommended_name, recommended_result = strategy_manager.recommend_strategy(
        market_conditions,
        analysis['statistics'],
        analysis['percentiles']
    )
    
    return {
        **analysis,
        'pricing_strategies': all_strategies,
        'recommended_strategy': recommended_name,
        'recommended_result': recommended_result,
        'market_conditions': market_conditions
    }

def analyze_pricing_strategy(ebay_result, strategy: Optional[PricingStrategy] = None):
    prices = []
    listings_data = []
    
    if hasattr(ebay_result, 'data') and ebay_result.data:
        for item in ebay_result.data:
            if hasattr(item, 'price') and item.price:
                try:
                    value = item.price.get('value', None)
                    if value is not None:
                        price_value = float(value)
                    else:
                        continue
                    prices.append(price_value)

                    title = getattr(item, 'title', '') or getattr(item, 'Title', '')
                    parsed_condition_title = parse_title_for_condition(title)
                    parsed_condition_description = parsed_description_for_condition(getattr(item, 'description', '') or getattr(item, 'Description', ''))
                    ebay_condition = getattr(item, 'condition', '')

                    final_condition = parsed_condition_title if parsed_condition_title != "Unknown" else parsed_condition_description if parsed_condition_description != "Unknown" else ebay_condition
                    
                    listing_info = {
                        'price': price_value,
                        'title': title,
                        'condition_parsed_title': parsed_condition_title,
                        'condition_parsed_description': parsed_condition_description,
                        'condition_ebay': ebay_condition,
                        'condition_final': final_condition,
                        'conditionId': getattr(item, 'conditionId', ''),
                        'item_id': getattr(item, 'itemId', ''),
                        'seller_username': getattr(item.seller, 'username', '') if hasattr(item, 'seller') else '',
                        'seller_feedback': getattr(item.seller, 'feedbackPercentage', 0) if hasattr(item, 'seller') else 0,
                        'shipping_cost': 0,
                        'item_url': getattr(item, 'itemWebUrl', ''),
                        'location': getattr(item.itemLocation, 'country', '') if hasattr(item, 'itemLocation') else ''
                    }

                    if hasattr(item, 'shippingOptions') and item.shippingOptions:
                        try:
                            shipping_option = item.shippingOptions[0]
                            if hasattr(shipping_option, 'shippingCost') and shipping_option.shippingCost:
                                listing_info['shipping_cost'] = float(shipping_option.shippingCost.value)
                        except:
                            pass
                    
                    listings_data.append(listing_info)
                except (ValueError, TypeError, AttributeError) as e:
                    print(f"Error processing item: {e}")
                    continue
    if not prices:
        return {"error": "No valid prices found in listings"}

    stats = {
        'total_listings': len(prices),
        'min_price': min(prices),
        'max_price': max(prices),
        'mean_price': statistics.mean(prices),
        'median_price': statistics.median(prices),
        'mode_price': statistics.mode(prices) if len(set(prices)) < len(prices) else None,
        'std_deviation': statistics.stdev(prices) if len(prices) > 1 else 0,
        'price_range': max(prices) - min(prices)
    }

    percentiles = {
        'p5': np.percentile(prices, 5),      # Bottom 5%
        'p10': np.percentile(prices, 10),    # Bottom 10%
        'p25': np.percentile(prices, 25),    # Q1
        'p50': np.percentile(prices, 50),    # Median
        'p75': np.percentile(prices, 75),    # Q3
        'p90': np.percentile(prices, 90),    # Top 10%
        'p95': np.percentile(prices, 95),    # Top 5%
        'p99': np.percentile(prices, 99)     # Top 1%
    }

    condition_breakdown = {}
    for listing in listings_data:
        condition = listing['condition_final']
        if condition not in condition_breakdown:
            condition_breakdown[condition] = {
                'prices': [],
                'listings': []
            }
        condition_breakdown[condition]['prices'].append(listing['price'])
        condition_breakdown[condition]['listings'].append(listing)
    
    # Calculate condition statistics
    condition_stats = {}
    for condition, data in condition_breakdown.items():
        prices_list = data['prices']
        if prices_list:
            condition_stats[condition] = {
                'count': len(prices_list),
                'avg_price': sum(prices_list) / len(prices_list),
                'min_price': min(prices_list),
                'max_price': max(prices_list),
                'median_price': sorted(prices_list)[len(prices_list)//2],
                'sample_listings': data['listings'][:3]  # First 3 as samples
            }

    return {
        'statistics': stats,
        'percentiles': percentiles,
        'condition_breakdown': condition_stats,
        'listings_data': listings_data[:10],
        'all_listings_count': len(listings_data),
        'condition_distribution': {k: v['count'] for k, v in condition_stats.items()}
    }

def enhanced_pricing_analysis(ebay_result,  strategies: Dict[str, PricingStrategy], market_conditions: Dict = None):
    """Enhanced analysis using Strategy pattern"""
    
    # Your existing analysis logic...
    analysis = analyze_pricing_strategy(ebay_result)
    if 'error' in analysis:
        return analysis
    
    # Default market conditions
    if market_conditions is None:
        market_conditions = {
            'volatility': analysis['statistics']['std_deviation'] / analysis['statistics']['mean_price'],
            'competition_level': 'high' if analysis['statistics']['total_listings'] > 20 else 'medium',
            'inventory_level': 'medium',
            'cash_flow_priority': False,
            'card_rarity': 'rare',  # Would come from card database
            'seller_reputation': 'high'
        }
    
    # Use strategy manager
    strategy_manager = PricingStrategyManager(strategies)
                                            
    
    # Get all strategies
    all_strategies = strategy_manager.get_all_strategies(
        analysis['statistics'], 
        analysis['percentiles'], 
        market_conditions
    )
    
    # Get recommendation
    recommended_name, recommended_result = strategy_manager.recommend_strategy(
        market_conditions,
        analysis['statistics'],
        analysis['percentiles']
    )
    
    return {
        **analysis,
        'pricing_strategies': all_strategies,
        'recommended_strategy': recommended_name,
        'recommended_result': recommended_result,
        'market_conditions': market_conditions
    }
