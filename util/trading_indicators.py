

def sma(data, window=14):
    return data.rolling(window=window).mean()

def ema(data, window=14):
    return data.ewm(span=window, adjust=False).mean()

def rsi(data, window=14):
    delta = data.diff(1)
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def macd(data, short_window=12, long_window=26, signal_window=9):
    short_ema = ema(data, short_window)
    long_ema = ema(data, long_window)
    macd = short_ema - long_ema
    signal = ema(macd, signal_window)
    return macd, signal
