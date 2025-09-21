import pandas as pd
import numpy as np
from typing import Dict, List, Optional
import warnings
import talib
warnings.filterwarnings('ignore')

class TechnicalIndicatorTrading:
    """
    Enhanced technical indicator trading system with weighted probabilities.

    This system assigns different weights to technical indicators based on:
    1. Research-backed importance and effectiveness
    2. Market conditions and volatility adaptations
    3. Indicator reliability and signal strength
    """

    def __init__(self, custom_weights: Optional[Dict[str, float]] = None):
        """
        Initialize with default or custom weights

        Args:
            custom_weights: Dictionary mapping indicator names to weights (0-1)
                          Keys: 'RSI', 'MACD', 'VWAP', 'BB', 'MA', 'EMA', 'CMF', 'CCI', 'STOCH', 'PSAR'
        """
        # Default weights based on research and effectiveness
        self.default_weights = {
            'RSI': 0.15,  # High reliability, momentum assessment
            'MACD': 0.15,  # Strong trend confirmation
            'VWAP': 0.12,  # Institutional benchmark
            'BB': 0.12,  # Volatility adaptive
            'MA': 0.10,  # Basic trend
            'EMA': 0.10,  # Responsive trend
            'CMF': 0.08,  # Volume confirmation
            'CCI': 0.08,  # Cyclical trends
            'STOCH': 0.05,  # More volatile signals
            'PSAR': 0.05  # Higher false signals
        }

        # Use custom weights if provided, otherwise use defaults
        if custom_weights:
            self.weights = {**self.default_weights, **custom_weights}
            # Normalize weights to sum to 1.0
            total_weight = sum(self.weights.values())
            self.weights = {k: v / total_weight for k, v in self.weights.items()}
        else:
            self.weights = self.default_weights

        # Validate weights sum to 1.0
        assert abs(sum(self.weights.values()) - 1.0) < 0.001, "Weights must sum to 1.0"

    def get_market_regime_weights(self, df: pd.DataFrame) -> Dict[str, float]:
        """
        Adjust weights based on market conditions (volatility, trend strength)

        Args:
            df: DataFrame with price data (must have lowercase column names)

        Returns:
            Adjusted weights dictionary
        """
        try:
            # Ensure we have the required columns (lowercase)
            if 'close' not in df.columns:
                print("Warning: 'close' column not found, using default weights")
                return self.weights

            if len(df) < 50:
                print("Warning: Insufficient data for market regime analysis, using default weights")
                return self.weights

            # Calculate market volatility (rolling standard deviation)
            returns = df['close'].pct_change().dropna()
            if len(returns) < 20:
                return self.weights

            volatility = returns.rolling(20, min_periods=10).std().iloc[-1]

            # Calculate trend strength (price vs 50-period MA)
            if len(df) >= 50:
                ma_50 = df['close'].rolling(50, min_periods=25).mean().iloc[-1]
                current_price = df['close'].iloc[-1]
                trend_strength = abs(current_price - ma_50) / ma_50 if ma_50 > 0 else 0
            else:
                trend_strength = 0

            adjusted_weights = self.weights.copy()

            # High volatility: Increase weight of volatility-adaptive indicators
            avg_volatility = returns.rolling(100, min_periods=50).std().mean()
            if volatility > avg_volatility and not pd.isna(volatility):
                adjusted_weights['BB'] *= 1.2  # Bollinger Bands more important
                adjusted_weights['VWAP'] *= 1.1  # VWAP stability valuable
                adjusted_weights['STOCH'] *= 0.8  # Reduce noisy oscillator
                adjusted_weights['PSAR'] *= 0.8  # Reduce trend-following in volatility

            # Strong trend: Increase weight of trend-following indicators
            if trend_strength > 0.05:  # 5% deviation from MA
                adjusted_weights['MACD'] *= 1.2
                adjusted_weights['EMA'] *= 1.1
                adjusted_weights['MA'] *= 1.1
                adjusted_weights['RSI'] *= 0.9  # RSI less reliable in strong trends

            # Normalize weights
            total_weight = sum(adjusted_weights.values())
            if total_weight > 0:
                adjusted_weights = {k: v / total_weight for k, v in adjusted_weights.items()}
            else:
                adjusted_weights = self.weights

            return adjusted_weights

        except Exception as e:
            print(f"Warning: Error in market regime analysis: {e}")
            return self.weights

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate all technical indicators using ta-lib library"""
        try:
            data = df.copy()

            # Ensure proper column names (lowercase)
            data.columns = data.columns.str.lower()

            # Check required columns
            required_cols = ['high', 'low', 'close', 'volume']
            missing_cols = [col for col in required_cols if col not in data.columns]
            if missing_cols:
                raise ValueError(f"Missing required columns: {missing_cols}")

            # Set date as index for VWAP calculation if date column exists
            date_col = None
            for col in ['date', 'datetime', 'timestamp']:
                if col in data.columns:
                    date_col = col
                    break

            if date_col:
                data = data.set_index(date_col)
                data.index = pd.to_datetime(data.index, errors='coerce')

            # Convert to numpy arrays for ta-lib (ta-lib works with numpy arrays)
            high = data['high'].values.astype(float)
            low = data['low'].values.astype(float)
            close = data['close'].values.astype(float)
            volume = data['volume'].values.astype(float)

            # Calculate all indicators with error handling
            try:
                data['ma'] = talib.SMA(close, timeperiod=20)
            except Exception as e:
                print(f"Warning: SMA calculation failed: {e}")
                data['ma'] = np.nan

            try:
                data['ema'] = talib.EMA(close, timeperiod=20)
            except Exception as e:
                print(f"Warning: EMA calculation failed: {e}")
                data['ema'] = np.nan

            try:
                data['rsi'] = talib.RSI(close, timeperiod=14)
            except Exception as e:
                print(f"Warning: RSI calculation failed: {e}")
                data['rsi'] = np.nan

            # MACD with error handling
            try:
                macd, macd_signal, macd_histogram = talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
                data['macd'] = macd
                data['macd_signal'] = macd_signal
                data['macd_histogram'] = macd_histogram
            except Exception as e:
                print(f"Warning: MACD calculation failed: {e}")
                data['macd'] = np.nan
                data['macd_signal'] = np.nan
                data['macd_histogram'] = np.nan

            # Bollinger Bands with error handling
            try:
                bb_upper, bb_middle, bb_lower = talib.BBANDS(close, timeperiod=20, nbdevup=2, nbdevdn=2, matype=0)
                data['bb_upper'] = bb_upper
                data['bb_middle'] = bb_middle
                data['bb_lower'] = bb_lower
            except Exception as e:
                print(f"Warning: Bollinger Bands calculation failed: {e}")
                data['bb_upper'] = np.nan
                data['bb_middle'] = np.nan
                data['bb_lower'] = np.nan

            # Stochastic with error handling
            try:
                stoch_k, stoch_d = talib.STOCH(high, low, close, fastk_period=14, slowk_period=3, slowk_matype=0,
                                               slowd_period=3, slowd_matype=0)
                data['stoch_k'] = stoch_k
                data['stoch_d'] = stoch_d
            except Exception as e:
                print(f"Warning: Stochastic calculation failed: {e}")
                data['stoch_k'] = np.nan
                data['stoch_d'] = np.nan

            # Chaikin Money Flow (CMF) - ta-lib doesn't have CMF, so we'll calculate it manually
            try:
                data['cmf'] = self._calculate_cmf(high, low, close, volume, period=21)
            except Exception as e:
                print(f"Warning: CMF calculation failed: {e}")
                data['cmf'] = np.nan

            # Commodity Channel Index (CCI)
            try:
                data['cci'] = talib.CCI(high, low, close, timeperiod=14)
            except Exception as e:
                print(f"Warning: CCI calculation failed: {e}")
                data['cci'] = np.nan

            # Parabolic SAR (PSAR)
            try:
                data['psar'] = talib.SAR(high, low, acceleration=0.02, maximum=0.2)
            except Exception as e:
                print(f"Warning: PSAR calculation failed: {e}")
                data['psar'] = np.nan

            # VWAP with error handling and fallback
            try:
                if date_col and data.index.dtype.kind == 'M':  # datetime index
                    data['vwap'] = self._calculate_vwap_with_date(data)
                else:
                    data['vwap'] = self._calculate_simple_vwap(data)
            except Exception as e:
                print(f"Warning: VWAP calculation failed, using fallback: {e}")
                data['vwap'] = self._calculate_simple_vwap(data)

            # Reset index to get date back as column if it was set
            if date_col and date_col not in data.columns:
                data = data.reset_index()

            return data

        except Exception as e:
            print(f"Error in calculate_indicators: {e}")
            return df

    def _calculate_cmf(self, high, low, close, volume, period=21):
        """Calculate Chaikin Money Flow since ta-lib doesn't have it"""
        try:
            # Money Flow Multiplier
            mf_multiplier = ((close - low) - (high - close)) / (high - low)

            # Handle division by zero
            mf_multiplier = np.where(high == low, 0, mf_multiplier)

            # Money Flow Volume
            mf_volume = mf_multiplier * volume

            # CMF calculation using pandas rolling for convenience
            mf_volume_series = pd.Series(mf_volume)
            volume_series = pd.Series(volume)

            cmf = mf_volume_series.rolling(window=period).sum() / volume_series.rolling(window=period).sum()

            return cmf.values
        except Exception as e:
            print(f"Error calculating CMF: {e}")
            return np.full(len(high), np.nan)

    def _calculate_vwap_with_date(self, data):
        """Calculate VWAP with date grouping"""
        try:
            # Group by date and calculate VWAP
            data['typical_price'] = (data['high'] + data['low'] + data['close']) / 3
            data['tp_volume'] = data['typical_price'] * data['volume']

            # Reset index temporarily to group by date
            temp_data = data.reset_index()
            temp_data['date_only'] = temp_data[temp_data.columns[0]].dt.date

            # Calculate cumulative VWAP for each date
            grouped = temp_data.groupby('date_only')
            vwap_list = []

            for _, group in grouped:
                cumulative_tp_volume = group['tp_volume'].cumsum()
                cumulative_volume = group['volume'].cumsum()
                group_vwap = cumulative_tp_volume / cumulative_volume
                vwap_list.extend(group_vwap.tolist())

            return np.array(vwap_list)
        except Exception as e:
            print(f"Error in VWAP calculation with date: {e}")
            return self._calculate_simple_vwap(data)

    def _calculate_simple_vwap(self, data):
        """Simple VWAP calculation fallback"""
        try:
            typical_price = (data['high'] + data['low'] + data['close']) / 3
            tp_volume = typical_price * data['volume']

            cumulative_tp_volume = tp_volume.cumsum()
            cumulative_volume = data['volume'].cumsum()

            vwap = cumulative_tp_volume / cumulative_volume
            return vwap.values
        except Exception as e:
            print(f"Error in simple VWAP calculation: {e}")
            return np.full(len(data), np.nan)

    def generate_signals(self, df: pd.DataFrame, adaptive_weights: bool = True) -> pd.DataFrame:
        """
        Generate weighted trading signals

        Args:
            df: Input DataFrame with OHLCV data
            adaptive_weights: Whether to adjust weights based on market conditions
        """
        # Ensure required columns exist (case insensitive)
        df_upper = df.copy()
        df_upper.columns = df_upper.columns.str.upper()

        required_cols = ['SYMBOL', 'OPEN', 'HIGH', 'LOW', 'CLOSE', 'VOLUME', 'DATE']
        missing_cols = [col for col in required_cols if col not in df_upper.columns]
        if missing_cols:
            raise ValueError(f"Required columns not found: {missing_cols}. Available columns: {list(df_upper.columns)}")

        # Convert to numeric and sort
        numeric_cols = ['OPEN', 'HIGH', 'LOW', 'CLOSE', 'VOLUME']
        for col in numeric_cols:
            df_upper[col] = pd.to_numeric(df_upper[col], errors='coerce')

        df_upper = df_upper.sort_values(['SYMBOL', 'DATE']).reset_index(drop=True)
        results = []

        # Process each symbol separately
        for symbol in df_upper['SYMBOL'].unique():
            symbol_data = df_upper[df_upper['SYMBOL'] == symbol].copy().reset_index(drop=True)

            if len(symbol_data) < 30:
                print(f"Warning: Insufficient data for symbol {symbol} ({len(symbol_data)} rows)")
                continue

            try:
                # Calculate technical indicators
                symbol_data = self.calculate_indicators(symbol_data)

                # Generate individual signals
                symbol_data = self._generate_individual_signals(symbol_data)

                # Get adaptive weights if enabled
                if adaptive_weights:
                    current_weights = self.get_market_regime_weights(symbol_data)
                else:
                    current_weights = self.weights

                # Calculate weighted probability
                symbol_data = self._calculate_weighted_probability(symbol_data, current_weights)

                results.append(symbol_data)

            except Exception as e:
                print(f"Error processing symbol {symbol}: {e}")
                continue

        if not results:
            raise ValueError("No valid data found for any symbols")

        final_results = pd.concat(results, ignore_index=True)

        # Ensure uppercase column names for output
        final_results.columns = final_results.columns.str.upper()
        # final_results = final_results.set_index('DATE')
        # final_results.index = pd.to_datetime(df.index)
        return final_results.drop(['MA', 'EMA', 'RSI', 'MACD', 'MACD_SIGNAL', 'MACD_HISTOGRAM', 'BB_UPPER',
                                   'BB_MIDDLE','BB_LOWER', 'STOCH_K', 'STOCH_D', 'CMF', 'CCI', 'PSAR', 'VWAP',
                                   'MA_SIGNAL', 'EMA_SIGNAL', 'RSI_SIGNAL', 'MACD_SIGNAL_IND', 'BB_SIGNAL',
                                   'STOCH_SIGNAL', 'CMF_SIGNAL', 'CCI_SIGNAL', 'PSAR_SIGNAL', 'VWAP_SIGNAL',
                                   'WEIGHTED_BUY_SCORE', 'WEIGHTED_SELL_SCORE', 'WEIGHTED_HOLD_SCORE',
                                   'APPLIED_WEIGHTS', 'TYPICAL_PRICE', 'TP_VOLUME'], axis=1)

    def _generate_individual_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate individual buy/sell/hold signals for each indicator"""

        # Fill NaN values with neutral values where appropriate
        df = df.fillna(0)

        # Individual signals
        df['ma_signal'] = np.where(df['close'] > df['ma'], 1,
                                   np.where(df['close'] < df['ma'], -1, 0))

        df['ema_signal'] = np.where(df['close'] > df['ema'], 1,
                                    np.where(df['close'] < df['ema'], -1, 0))

        # RSI with NaN handling
        df['rsi_signal'] = np.where((df['rsi'] < 30) & (~pd.isna(df['rsi'])), 1,
                                    np.where((df['rsi'] > 70) & (~pd.isna(df['rsi'])), -1, 0))

        # Enhanced MACD signal
        df['macd_signal_ind'] = np.where(
            (df['macd'] > df['macd_signal']) & (~pd.isna(df['macd'])) & (~pd.isna(df['macd_signal'])), 1,
            np.where(
                (df['macd'] < df['macd_signal']) & (~pd.isna(df['macd'])) & (~pd.isna(df['macd_signal'])), -1, 0
            )
        )

        # Bollinger Bands
        df['bb_signal'] = np.where(
            (df['close'] < df['bb_lower']) & (~pd.isna(df['bb_lower'])), 1,
            np.where(
                (df['close'] > df['bb_upper']) & (~pd.isna(df['bb_upper'])), -1, 0
            )
        )

        df['stoch_signal'] = np.where(
            (df['stoch_k'] < 20) & (df['stoch_d'] < 20) & (~pd.isna(df['stoch_k'])) & (~pd.isna(df['stoch_d'])), 1,
            np.where(
                (df['stoch_k'] > 80) & (df['stoch_d'] > 80) & (~pd.isna(df['stoch_k'])) & (~pd.isna(df['stoch_d'])), -1,
                0
            )
        )

        df['cmf_signal'] = np.where((df['cmf'] > 0.1) & (~pd.isna(df['cmf'])), 1,
                                    np.where((df['cmf'] < -0.1) & (~pd.isna(df['cmf'])), -1, 0))

        df['cci_signal'] = np.where((df['cci'] < -100) & (~pd.isna(df['cci'])), 1,
                                    np.where((df['cci'] > 100) & (~pd.isna(df['cci'])), -1, 0))

        df['psar_signal'] = np.where(
            (df['close'] > df['psar']) & (~pd.isna(df['psar'])), 1,
            np.where(
                (df['close'] < df['psar']) & (~pd.isna(df['psar'])), -1, 0
            )
        )

        df['vwap_signal'] = np.where(
            (df['close'] > df['vwap']) & (~pd.isna(df['vwap'])), 1,
            np.where(
                (df['close'] < df['vwap']) & (~pd.isna(df['vwap'])), -1, 0
            )
        )

        return df

    def _calculate_weighted_probability(self, df: pd.DataFrame, weights: Dict[str, float]) -> pd.DataFrame:
        """Calculate weighted probabilities for BUY, HOLD, SELL decisions"""

        # Map indicator names to signal column names
        indicator_mapping = {
            'MA': 'ma_signal',
            'EMA': 'ema_signal',
            'RSI': 'rsi_signal',
            'MACD': 'macd_signal_ind',
            'BB': 'bb_signal',
            'STOCH': 'stoch_signal',
            'CMF': 'cmf_signal',
            'CCI': 'cci_signal',
            'PSAR': 'psar_signal',
            'VWAP': 'vwap_signal'
        }

        # Fill NaN values with 0 (HOLD)
        for col in indicator_mapping.values():
            if col in df.columns:
                df[col] = df[col].fillna(0)

        # Calculate weighted scores for each row
        df['weighted_buy_score'] = 0.0
        df['weighted_sell_score'] = 0.0
        df['weighted_hold_score'] = 0.0

        for indicator, signal_col in indicator_mapping.items():
            if signal_col in df.columns and indicator in weights:
                weight = weights[indicator]

                # Add weighted contribution for each signal type
                df['weighted_buy_score'] += (df[signal_col] == 1).astype(float) * weight
                df['weighted_sell_score'] += (df[signal_col] == -1).astype(float) * weight
                df['weighted_hold_score'] += (df[signal_col] == 0).astype(float) * weight

        # Convert to probabilities (percentages)
        df['buy'] = df['weighted_buy_score']
        df['sell'] = df['weighted_sell_score']
        df['keep'] = df['weighted_hold_score']

        # Final recommendation based on highest weighted probability
        df['recommendation'] = df.apply(
            lambda row: 'BUY' if row['buy'] >= max(row['sell'], row['keep'])
            else 'SELL' if row['sell'] >= row['keep']
            else 'HOLD', axis=1
        )

        # Enhanced confidence score
        df['confidence'] = df.apply(
            lambda row: abs(max(row['buy'], row['sell'], row['keep']) -
                            sorted([row['buy'], row['sell'], row['keep']])[-2]),
            axis=1
        )

        # Add weight information for transparency
        df['applied_weights'] = str(weights)

        return df



def create_sample_data(symbols: List[str] = ['AAPL', 'GOOGL', 'MSFT'], days: int = 100) -> pd.DataFrame:
    """Create sample stock data for demonstration"""
    np.random.seed(42)
    all_data = []
    base_date = pd.Timestamp('2024-01-01')

    for symbol in symbols:
        base_price = np.random.uniform(50, 200)
        dates = pd.date_range(base_date, periods=days, freq='D')

        returns = np.random.normal(0.001, 0.02, days)
        prices = [base_price]

        for ret in returns[1:]:
            new_price = prices[-1] * (1 + ret)
            prices.append(max(new_price, 1))

        for i, (date, close) in enumerate(zip(dates, prices)):
            volatility = abs(np.random.normal(0, 0.01))
            high = close * (1 + volatility)
            low = close * (1 - volatility)
            open_price = low + (high - low) * np.random.random()

            high = max(high, open_price, close)
            low = min(low, open_price, close)
            volume = int(np.random.lognormal(12, 1))

            all_data.append({
                'SYMBOL': symbol,
                'DATE': date,
                'OPEN': round(open_price, 2),
                'HIGH': round(high, 2),
                'LOW': round(low, 2),
                'CLOSE': round(close, 2),
                'VOLUME': volume
            })

    return pd.DataFrame(all_data)


def main():
    """Main function to demonstrate weighted trading system"""
    print("Weighted Technical Indicator Trading System - Fixed Version")
    print("=" * 70)

    try:
        # Initialize trading system with default weights
        trading_system = TechnicalIndicatorTrading()

        # Create sample data
        print("\n1. Creating sample data...")
        sample_data = create_sample_data(['AAPL', 'GOOGL', 'MSFT'], days=60)
        print(f"Sample data created: {len(sample_data)} rows for {sample_data['SYMBOL'].nunique()} symbols")

        # Generate weighted signals
        print("\n2. Calculating weighted technical indicators and signals...")
        results = trading_system.generate_signals(sample_data, adaptive_weights=True)
        print("Weighted technical indicators calculated successfully!")

        print(results.columns)
        # Display results
        print("\n3. Weighted Results Summary:")
        print("-" * 35)

        latest_signals = results.groupby('SYMBOL').tail(1)[
            ['SYMBOL', 'DATE', 'CLOSE', 'BUY', 'SELL',
             'KEEP', 'RECOMMENDATION', 'CONFIDENCE']
        ]

        print("\nLatest Weighted Trading Signals:")
        print(latest_signals.to_string(index=False))

        return results, trading_system

    except Exception as e:
        print(f"Error in main execution: {e}")
        import traceback
        traceback.print_exc()
        return None, None


# if __name__ == "__main__":
#     results, system = main()
