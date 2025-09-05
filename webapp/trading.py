import pandas as pd
import pandas_ta as ta
import numpy as np

def calculate_technical_indicators(df):
    # Calculate indicators
    df['MA'] = ta.sma(df['CLOSE'], length=14)
    df['EMA'] = ta.ema(df['CLOSE'], length=14)
    df['RSI'] = ta.rsi(df['CLOSE'], length=14)
    # macd = ta.macd(df['CLOSE'])
    # df['MACD'] = macd.iloc[:, 0]
    # df['MACD_signal'] = macd.iloc[:, 2]
    macd = calculate_macd(df['CLOSE'])
    df['MACD'] = macd.iloc[:, 0]
    df['MACD_signal'] = macd.iloc[:, 2]
    bb = ta.bbands(df['CLOSE'], length=14)
    df['BB_upper'] = bb.iloc[:, 2]
    df['BB_middle'] = bb.iloc[:, 1]
    df['BB_lower'] = bb.iloc[:, 0]
    df['STOCH_k'] = ta.stoch(df['HIGH'], df['LOW'], df['CLOSE'])['STOCHk_14_3_3']
    df['STOCH_d'] = ta.stoch(df['HIGH'], df['LOW'], df['CLOSE'])['STOCHd_14_3_3']
    # data['ATR'] = ta.atr(data['HIGH'], data['LOW'], data['CLOSE'], length=14)
    df['CMF'] = ta.cmf(df['HIGH'], df['LOW'], df['CLOSE'], df['VOLUME'])
    df['CCI'] = ta.cci(df['HIGH'], df['LOW'], df['CLOSE'], length=14)
    df['PSAR'] = ta.psar(df['HIGH'], df['LOW'], df['CLOSE']).iloc[:, 0]
    df = df.set_index('DATE')
    df.index = pd.to_datetime(df.index)
    df['VWAP'] = ta.vwap(df['HIGH'], df['LOW'], df['CLOSE'], df['VOLUME'])
    return df

def calculate_macd(data, fast_length=12, slow_length=26, signal_length=9):

    if not isinstance(data, (pd.Series, np.ndarray)):
      return pd.DataFrame() # Handle invalid input

    if isinstance(data, np.ndarray):
        data = pd.Series(data) # Convert numpy array to pandas Series if needed

    if len(data) < slow_length: # Need enough data points for calculations
       return pd.DataFrame()

    fast_ema = data.ewm(span=fast_length, adjust=False).mean()
    slow_ema = data.ewm(span=slow_length, adjust=False).mean()

    macd = fast_ema - slow_ema
    signal = macd.ewm(span=signal_length, adjust=False).mean()
    histogram = macd - signal

    df = pd.DataFrame({'MACD': macd, 'MACD_signal': signal, 'Histogram': histogram})
    return df


# Define decision boundaries
def decision_ma(row):
    tau = 0.01
    if row['CLOSE'] >= (1+tau)*row['MA']:
        return "Buy"
    elif row['CLOSE'] <= (1-tau)*row['MA']:
        return "Sell"
    else:
        return "Keep"


def decision_ema(row):
    tau = 0.01
    if row['CLOSE'] >= (1+tau)*row['EMA']:
        return "Buy"
    elif row['CLOSE'] <= (1-tau)*row['EMA']:
        return "Sell"
    else:
        return "Keep"


def decision_rsi(row):
    if row['RSI'] < 30:
        return "Buy"
    elif row['RSI'] > 70:
        return "Sell"
    else:
        return "Keep"


def decision_macd(row):
    tau = 0.01
    if row['MACD'] >= (1+tau)*row['MACD_signal']:
        return "Buy"
    elif row['MACD'] <= (1-tau)*row['MACD_signal']:
        return "Sell"
    else:
        return "Keep"


def decision_bb(row):
    if row['CLOSE'] <= row['BB_lower']:
        return "Buy"
    elif row['CLOSE'] >= row['BB_upper']:
        return "Sell"
    else:
        return "Keep"


def decision_stoch(row):
    if row['STOCH_k'] < 20:
        return "Buy"
    elif row['STOCH_k'] > 80:
        return "Sell"
    else:
        return "Keep"


def decision_cmf(row):
    if row['CMF'] > 0.1:
        return 'Buy'
    elif row['CMF'] < -0.1:
        return 'Sell'
    else:
        return 'Keep'


def decision_cci(row):
    if row['CCI'] < -100:
        return "Buy"
    elif row['CCI'] > 100:
        return "Sell"
    else:
        return "Keep"


def decision_psar(row):
    tau = 0.01
    if row['CLOSE'] >= (1+tau)*row['PSAR']:
        return "Buy"
    elif row['CLOSE'] <= (1-tau)*row['PSAR']:
        return "Sell"
    else:
        return "Keep"


def decision_vwap(row):
    tau = 0.01
    if row['CLOSE'] >= (1+tau)*row['VWAP']:
        return "Buy"
    elif row['CLOSE'] <= (1-tau)*row['VWAP']:
        return "Sell"
    else:
        return "Keep"

# Define coefficients for each indicator
indicators_proba = {
    'ma': 0.10,
    'ema': 0.10,
    'rsi': 0.15,
    'macd': 0.15,
    'bb': 0.10,
    'stoch': 0.10,
    'cmf': 0.05,
    'cci': 0.05,
    'psar': 0.10,
    'vwap': 0.10
}

def scores(row):
    # dico = [(k.split('_')[-1].upper(),v) for (k,v) in globals().items() if k.startswith("decision")]
    decision_scores = {'Buy':0, 'Sell':0, 'Keep':0}
    l = []
    for (i, p) in indicators_proba.items():
        function = globals()[f'decision_{i}']
        decision = function(row)
        decision_scores[decision] = decision_scores[decision] + p
    return pd.Series(decision_scores)

def get_trading_decisions(data):
    symbols = set(data['SYMBOL'])
    df = data.sort_values(by='DATE', ascending=True)
    result = []
    for symbol in symbols:
        df_tmp = df[df["SYMBOL"]==symbol].copy()
        data = calculate_technical_indicators(df_tmp)
        data[['Buy', 'Sell', 'Keep']] = data.apply(scores, axis=1)
        data = data.drop(['MA', 'EMA', 'RSI', 'MACD', 'MACD_signal', 'BB_upper', 'BB_middle', 'BB_lower',
                          'STOCH_k', 'STOCH_d', 'CMF', 'CCI', 'PSAR', 'VWAP'], axis=1)
        result = result + [data]
    return pd.concat(result).sort_values(by=['Buy', 'DIVIDEND'])


