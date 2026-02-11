from datetime import datetime
import numpy as np
import pandas as pd
from scipy.stats import skew, kurtosis
#log returns, segemented by rarity,set, card type and day since release release-> detect spikes, volatility regimes
##metric-> mean, std, kewness, kurtosis, tail riks (95 percentile)
def log_return_metrics(x, released_date : datetime, windows: list[int]):
        
        x = x[x["date"] >= pd.Timestamp(released_date)].sort_values("date")

        prices = x["price_avg"].to_numpy()
        
        if len(prices) < 2:
            return pd.Series({
                "log_return_mean": np.nan,
                "log_return_std": np.nan,
                "log_return_skew": np.nan,
                "log_return_kurtosis": np.nan,
                "log_return_95pct": np.nan,
                "n_observations": len(prices)
            })
    
        log_returns = np.diff(np.log(prices))
        if len(log_returns) == 0:
            return pd.Series({
                "log_return_mean": np.nan,
                "log_return_std": np.nan,
                "log_return_skew": np.nan,
                "log_return_kurtosis": np.nan,
                "log_return_95pct": np.nan,
                "n_observations": len(prices)
            })
        series = {}
        for window in windows:
            window_prices = prices = x["price_avg"].values[:window+1]
            if len(log_returns) < window_prices:
                series.update({
                    f"log_return_mean_{window_prices}": np.nan,
                    f"log_return_std_{window_prices}": np.nan,
                    f"log_return_skew_{window_prices}": np.nan,
                    f"log_return_kurtosis_{window_prices}": np.nan,
                    f"log_return_95pct_{window_prices}": np.nan,
                    f"n_observations_{window_prices}": len(prices)
                })
            else:
                windowed_returns = log_returns[-window_prices:]
                series.update({
                    f"log_return_mean_{window_prices}": np.mean(windowed_returns),
                    f"log_return_std_{window_prices}": np.std(windowed_returns),
                    f"log_return_skew_{window_prices}": skew(windowed_returns),
                    f"log_return_kurtosis_{window_prices}": kurtosis(windowed_returns),
                    f"log_return_95pct_{window_prices}": np.percentile(windowed_returns, 95),
                    f"n_observations_{window_prices}": len(prices)
                })
        return pd.Series(series)

def calculate_log_returns_since_release_by_windows(price_df, released_date : datetime, segmented_by : list[str], windows: list[int]):
    """calculate log returns for price dataframe, segmented by given columns. Metrics are mean, std , skewness, kurtosis, 95 percentile"""
    #whatch out for null prices -> set to 0.001 to avoid log(0)
    # segement by set_code, rarity, finish, card_type, days_since_release
    metrics_df = (price_df
                  .groupby(segmented_by)
                  .apply(log_return_metrics, released_date=released_date, windows=windows)
                  .reset_index())
    return metrics_df

#market analysis-> median liquidity per decile, volatilty , raroty et age distribution per decile, reprint frequency
##waht types are in the top deciles

#prices after release-> time to low, time to peak, segemente rarity, set size, rotation status. price could be normalise by the price at release or prerelease
# ##look at long term trends in prices after release

#conditional of gaining X% after X days P(price >= (1 + x%) * price_at_day_d | survived to day_d), for survival vurves, CDF, segemented by rarity, set size, rotation status

## volatility clustering - cluster cards based on their volatility profiles over time - identify common patterns, stable and speculative cards

## Liquidity vs appreciation -> number listing , volume /sale count

## reprint riskl impact

## release month analysis -> seasonality effects on prices and liquidity

## card similarity clustering - cluster cards based on attributes and price behavior - identify simialr cards for comparative analysis: good for cold start prediction

## regime predition -> a time if speculation or holding? (markov chain)