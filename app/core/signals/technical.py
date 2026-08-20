"""Vectorized technical analysis engine calculating 10 TA indicators."""
import pandas as pd
import numpy as np

def calculate_technical_indicators(df_price: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates 10 technical indicators:
    RSI, MACD, VWAP, BB, MA, EMA, CMF, CCI, STOCH, PSAR.
    """
    if df_price.empty or len(df_price) < 20:
        return df_price

    df = df_price.copy().sort_values('date').reset_index(drop=True)
    close = df['close']
    high = df['high']
    low = df['low']
    volume = df['volume'].fillna(0)

    # 1. RSI (14-period)
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss.replace(0, np.nan))
    df['rsi'] = 100 - (100 / (1 + rs))

    # 2. MACD (12, 26, 9)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df['macd'] = ema12 - ema26
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']

    # 3. VWAP
    typical_price = (high + low + close) / 3
    df['vwap'] = (typical_price * volume).cumsum() / (volume.cumsum().replace(0, np.nan))

    # 4. Bollinger Bands (20, 2)
    df['bb_middle'] = close.rolling(window=20).mean()
    std20 = close.rolling(window=20).std()
    df['bb_upper'] = df['bb_middle'] + (std20 * 2)
    df['bb_lower'] = df['bb_middle'] - (std20 * 2)

    # 5. Simple Moving Averages (MA20, MA50, MA200)
    df['ma20'] = close.rolling(window=20).mean()
    df['ma50'] = close.rolling(window=50).mean()
    df['ma200'] = close.rolling(window=200).mean()

    # 6. Exponential Moving Averages (EMA9, EMA21, EMA50)
    df['ema9'] = close.ewm(span=9, adjust=False).mean()
    df['ema21'] = close.ewm(span=21, adjust=False).mean()
    df['ema50'] = close.ewm(span=50, adjust=False).mean()

    # 7. Chaikin Money Flow (CMF 20)
    mf_multiplier = np.where((high - low) == 0, 0, ((close - low) - (high - close)) / (high - low))
    mf_volume = mf_multiplier * volume
    df['cmf'] = mf_volume.rolling(window=20).sum() / (volume.rolling(window=20).sum().replace(0, np.nan))

    # 8. Commodity Channel Index (CCI 20)
    tp = (high + low + close) / 3
    sma_tp = tp.rolling(window=20).mean()
    mad = tp.rolling(window=20).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    df['cci'] = (tp - sma_tp) / (0.015 * mad.replace(0, np.nan))

    # 9. Stochastic Oscillator (STOCH 14, 3)
    low14 = low.rolling(window=14).min()
    high14 = high.rolling(window=14).max()
    df['stoch_k'] = 100 * ((close - low14) / (high14 - low14).replace(0, np.nan))
    df['stoch_d'] = df['stoch_k'].rolling(window=3).mean()

    # 10. Parabolic SAR (PSAR)
    psar = close.copy()
    af = 0.02
    max_af = 0.20
    ep = high.iloc[0]
    psar.iloc[0] = low.iloc[0]
    bull = True

    for i in range(1, len(df)):
        prior_psar = psar.iloc[i-1]
        if bull:
            psar.iloc[i] = prior_psar + af * (ep - prior_psar)
            if low.iloc[i] < psar.iloc[i]:
                bull = False
                psar.iloc[i] = ep
                ep = low.iloc[i]
                af = 0.02
            else:
                if high.iloc[i] > ep:
                    ep = high.iloc[i]
                    af = min(af + 0.02, max_af)
        else:
            psar.iloc[i] = prior_psar + af * (ep - prior_psar)
            if high.iloc[i] > psar.iloc[i]:
                bull = True
                psar.iloc[i] = ep
                ep = high.iloc[i]
                af = 0.02
            else:
                if low.iloc[i] < ep:
                    ep = low.iloc[i]
                    af = min(af + 0.02, max_af)
    df['psar'] = psar

    return df

def generate_technical_signal_consensus(df_ta: pd.DataFrame) -> dict:
    """Generates consensus short-term trade signal based on recent TA indicators."""
    if df_ta.empty or 'rsi' not in df_ta.columns:
        return {"signal": "NEUTRAL", "bullish_count": 0, "bearish_count": 0}
    
    latest = df_ta.iloc[-1]
    bullish = 0
    bearish = 0

    if pd.notnull(latest.get('rsi')):
        if latest['rsi'] < 30: bullish += 1
        elif latest['rsi'] > 70: bearish += 1

    if pd.notnull(latest.get('macd')) and pd.notnull(latest.get('macd_signal')):
        if latest['macd'] > latest['macd_signal']: bullish += 1
        else: bearish += 1

    if pd.notnull(latest.get('close')) and pd.notnull(latest.get('vwap')):
        if latest['close'] > latest['vwap']: bullish += 1
        else: bearish += 1

    if pd.notnull(latest.get('close')) and pd.notnull(latest.get('ma50')):
        if latest['close'] > latest['ma50']: bullish += 1
        else: bearish += 1

    if pd.notnull(latest.get('cmf')):
        if latest['cmf'] > 0: bullish += 1
        else: bearish += 1

    signal = "NEUTRAL"
    if bullish >= 4: signal = "STRONG BUY"
    elif bullish == 3: signal = "BUY"
    elif bearish >= 4: signal = "STRONG SELL"
    elif bearish == 3: signal = "SELL"

    return {
        "signal": signal,
        "bullish_count": bullish,
        "bearish_count": bearish,
        "rsi": latest.get('rsi'),
        "macd": latest.get('macd'),
        "close": latest.get('close')
    }
