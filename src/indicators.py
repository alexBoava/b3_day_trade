import numpy as np
import pandas as pd

def calculate_ema(series: pd.Series, period: int) -> pd.Series:
    """Calcula a Média Móvel Exponencial (EMA)."""
    return series.ewm(span=period, adjust=False).mean()

def calculate_sma(series: pd.Series, period: int) -> pd.Series:
    """Calcula a Média Móvel Simples (SMA)."""
    return series.rolling(window=period).mean()

def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    Calcula o IFR (Índice de Força Relativa / RSI) utilizando
    a suavização exponencial clássica de Wilder.
    """
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    # Suavização de Wilder (alpha = 1 / period)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    # Para divisões por zero ou sem perdas:
    rsi = rsi.fillna(50.0)
    return rsi

def calculate_macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """Calcula a linha MACD, a Linha de Sinal e o Histograma MACD."""
    ema_fast = calculate_ema(series, fast)
    ema_slow = calculate_ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = calculate_ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def calculate_bollinger_bands(series: pd.Series, period: int = 20, num_std: float = 2.0):
    """Calcula as Bandas de Bollinger (Superior, Média e Inferior)."""
    sma = calculate_sma(series, period)
    std = series.rolling(window=period).std()
    upper = sma + (std * num_std)
    lower = sma - (std * num_std)
    bandwidth = (upper - lower) / sma
    return upper, sma, lower, bandwidth

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calcula o Average True Range (ATR) para volatilidade e stop loss."""
    high = df['High']
    low = df['Low']
    close_prev = df['Close'].shift(1)

    tr1 = high - low
    tr2 = (high - close_prev).abs()
    tr3 = (low - close_prev).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    return atr

def detect_candlestick_patterns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Identifica padrões gráficos de reversão comuns para Swing Trade:
    - Martelo (Hammer)
    - Engolfo de Alta (Bullish Engulfing)
    - Inside Bar
    """
    patterns = pd.DataFrame(index=df.index)

    o, h, l, c = df['Open'], df['High'], df['Low'], df['Close']
    body = (c - o).abs()
    candle_range = (h - l).replace(0, 0.001)

    # Martelo: pavio inferior >= 2x corpo, pavio superior pequeno (<= 15% da amplitude)
    lower_wick = np.where(c >= o, o - l, c - l)
    upper_wick = np.where(c >= o, h - c, h - o)
    is_hammer = (lower_wick >= 2.0 * body) & (upper_wick <= 0.2 * candle_range) & (candle_range > 0)
    patterns['Hammer'] = is_hammer

    # Engolfo de Alta: candle anterior vermelho, candle atual verde engolfando o corpo anterior
    prev_o, prev_c = o.shift(1), c.shift(1)
    is_engulfing = (prev_c < prev_o) & (c > o) & (c >= prev_o) & (o <= prev_c)
    patterns['Bullish_Engulfing'] = is_engulfing.fillna(False)

    # Inside Bar: máxima menor que anterior e mínima maior que anterior
    is_inside = (h < h.shift(1)) & (l > l.shift(1))
    patterns['Inside_Bar'] = is_inside.fillna(False)

    return patterns

def calculate_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aplica todos os indicadores técnicos necessários ao DataFrame de candles.
    Retorna uma cópia do DataFrame com as colunas calculadas.
    """
    if df.empty or len(df) < 20:
        return df

    res = df.copy()

    # Médias Móveis Exponenciais
    res['EMA9'] = calculate_ema(res['Close'], 9)
    res['EMA20'] = calculate_ema(res['Close'], 20)
    res['EMA50'] = calculate_ema(res['Close'], 50)
    res['EMA200'] = calculate_ema(res['Close'], 200)

    # IFR (RSI 14)
    res['RSI'] = calculate_rsi(res['Close'], 14)

    # MACD
    macd, signal, hist = calculate_macd(res['Close'], 12, 26, 9)
    res['MACD'] = macd
    res['MACD_Signal'] = signal
    res['MACD_Hist'] = hist

    # Bandas de Bollinger
    bb_upper, bb_mid, bb_lower, bb_width = calculate_bollinger_bands(res['Close'], 20, 2.0)
    res['BB_Upper'] = bb_upper
    res['BB_Mid'] = bb_mid
    res['BB_Lower'] = bb_lower
    res['BB_Width'] = bb_width

    # ATR
    res['ATR'] = calculate_atr(res, 14)

    # Volume Médio
    if 'Volume' in res.columns:
        res['Volume_MA20'] = calculate_sma(res['Volume'], 20)
        res['Volume_Ratio'] = res['Volume'] / res['Volume_MA20'].replace(0, np.nan)
        res['Volume_Ratio'] = res['Volume_Ratio'].fillna(1.0)
    else:
        res['Volume_MA20'] = np.nan
        res['Volume_Ratio'] = 1.0

    # Padrões de Candle
    patterns = detect_candlestick_patterns(res)
    res['Pattern_Hammer'] = patterns['Hammer']
    res['Pattern_Engulfing'] = patterns['Bullish_Engulfing']
    res['Pattern_InsideBar'] = patterns['Inside_Bar']

    # Setup 9.1 de Larry Williams:
    # EMA9 virou para cima: EMA9 atual > EMA9 anterior e EMA9 anterior <= EMA9 antepenúltimo
    ema9 = res['EMA9']
    ema9_shift1 = ema9.shift(1)
    ema9_shift2 = ema9.shift(2)
    res['Setup_9_1'] = (ema9 > ema9_shift1) & (ema9_shift1 <= ema9_shift2) & (res['Close'] > ema9)

    return res
