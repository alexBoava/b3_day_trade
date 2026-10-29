import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, Tuple

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

    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
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
    bandwidth = (upper - lower) / sma.replace(0, np.nan)
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

    lower_wick = np.where(c >= o, o - l, c - l)
    upper_wick = np.where(c >= o, h - c, h - o)
    is_hammer = (lower_wick >= 2.0 * body) & (upper_wick <= 0.2 * candle_range) & (candle_range > 0)
    patterns['Hammer'] = is_hammer

    prev_o, prev_c = o.shift(1), c.shift(1)
    is_engulfing = (prev_c < prev_o) & (c > o) & (c >= prev_o) & (o <= prev_c)
    patterns['Bullish_Engulfing'] = is_engulfing.fillna(False)

    is_inside = (h < h.shift(1)) & (l > l.shift(1))
    patterns['Inside_Bar'] = is_inside.fillna(False)

    return patterns

def detect_rsi_bullish_divergence(df: pd.DataFrame, lookback: int = 25) -> Dict[str, Any]:
    """
    Detecta Divergência de Alta no IFR (Bullish Divergence):
    Ocorre quando o Preço atinge um fundo mais baixo (ou igual),
    enquanto o IFR(14) faz um fundo claramente mais alto,
    indicando esgotamento da força vendedora e reversão iminente.
    """
    if len(df) < lookback:
        return {"detected": False}

    window = df.iloc[-lookback:].copy()
    if 'RSI' not in window.columns:
        return {"detected": False}

    # Dividir a janela em dois períodos: Fundo Anterior (bars 5 a 22 atrás) e Fundo Recente (últimos 5 bars)
    recent_bars = window.iloc[-6:]
    prior_bars = window.iloc[-24:-6]

    if prior_bars.empty or recent_bars.empty:
        return {"detected": False}

    # Fundo anterior
    idx_min_prior = prior_bars['Low'].idxmin()
    low_prior = float(prior_bars.loc[idx_min_prior, 'Low'])
    rsi_prior = float(prior_bars.loc[idx_min_prior, 'RSI'])

    # Fundo recente
    idx_min_recent = recent_bars['Low'].idxmin()
    low_recent = float(recent_bars.loc[idx_min_recent, 'Low'])
    rsi_recent = float(recent_bars.loc[idx_min_recent, 'RSI'])

    # Condições matemáticas para Divergência de Alta Clássica:
    # 1. Preço fez fundo menor ou praticamente igual (até 1.5% de margem)
    price_lower_or_equal = low_recent <= (low_prior * 1.015)

    # 2. IFR fez fundo expressivamente mais alto (+2.5 pontos acima)
    rsi_higher = rsi_recent >= (rsi_prior + 2.5)

    # 3. O fundo anterior deve ter ocorrido em sobrevenda ou correção forte (RSI <= 42)
    prior_was_oversold = rsi_prior <= 42.0

    # 4. Gatilho de confirmação recente: último candle reagiu (fechamento positivo ou superando mínima)
    last_candle = df.iloc[-1]
    reversal_reaction = (last_candle['Close'] >= last_candle['Open']) or (last_candle['Close'] > df['Close'].iloc[-2])

    if price_lower_or_equal and rsi_higher and prior_was_oversold and reversal_reaction:
        return {
            "detected": True,
            "low_recent": round(low_recent, 2),
            "low_prior": round(low_prior, 2),
            "rsi_recent": round(rsi_recent, 1),
            "rsi_prior": round(rsi_prior, 1),
            "date_prior": idx_min_prior.strftime('%d/%m') if hasattr(idx_min_prior, 'strftime') else str(idx_min_prior),
            "date_recent": idx_min_recent.strftime('%d/%m') if hasattr(idx_min_recent, 'strftime') else str(idx_min_recent),
            "reason": (
                f"Divergência de Alta: Preço renovou fundo (R$ {low_recent:.2f} <= R$ {low_prior:.2f}), "
                f"mas IFR formou fundo mais alto ({rsi_recent:.1f} > {rsi_prior:.1f}). Esgotamento vendedor!"
            )
        }

    return {"detected": False}

def calculate_relative_strength(
    df_asset: pd.DataFrame,
    df_benchmark: Optional[pd.DataFrame]
) -> Dict[str, Any]:
    """
    Calcula a Força Relativa (Alpha) da ação contra o benchmark (BOVA11 / Ibovespa)
    em janelas de 20 pregões (curto prazo) e 60 pregões (médio prazo).
    """
    if df_asset.empty or df_benchmark is None or df_benchmark.empty:
        return {
            "alpha_20d": 0.0,
            "alpha_60d": 0.0,
            "rs_status": "Neutro",
            "rs_badge": "⚪ Neutro",
            "is_outperforming": False
        }

    # Alinhar datas comuns
    common_dates = df_asset.index.intersection(df_benchmark.index)
    if len(common_dates) < 25:
        return {
            "alpha_20d": 0.0,
            "alpha_60d": 0.0,
            "rs_status": "Dados insuficientes",
            "rs_badge": "⚪ Neutro",
            "is_outperforming": False
        }

    c_asset = df_asset.loc[common_dates, 'Close']
    c_bench = df_benchmark.loc[common_dates, 'Close']

    # Retorno percentual 20 pregões (~1 mês)
    p20 = min(21, len(common_dates))
    ret_asset_20 = ((c_asset.iloc[-1] / c_asset.iloc[-p20]) - 1.0) * 100.0
    ret_bench_20 = ((c_bench.iloc[-1] / c_bench.iloc[-p20]) - 1.0) * 100.0
    alpha_20d = round(ret_asset_20 - ret_bench_20, 1)

    # Retorno percentual 60 pregões (~3 meses)
    p60 = min(61, len(common_dates))
    ret_asset_60 = ((c_asset.iloc[-1] / c_asset.iloc[-p60]) - 1.0) * 100.0
    ret_bench_60 = ((c_bench.iloc[-1] / c_bench.iloc[-p60]) - 1.0) * 100.0
    alpha_60d = round(ret_asset_60 - ret_bench_60, 1)

    # Razão de Preço (Ratio Line) e sua média
    ratio = c_asset / c_bench
    ratio_ma = calculate_ema(ratio, 20)
    ratio_trending_up = float(ratio.iloc[-1]) > float(ratio_ma.iloc[-1])

    if alpha_20d >= 4.0 and ratio_trending_up:
        status = "Forte Liderança"
        badge = f"🚀 Líder (+{alpha_20d:.1f}%)"
        is_out = True
    elif alpha_20d > 0.0:
        status = "Superando o Ibov"
        badge = f"🟢 Acima Ibov (+{alpha_20d:.1f}%)"
        is_out = True
    elif -3.5 <= alpha_20d <= 0.0:
        status = "Alinhado ao Ibov"
        badge = f"🟡 Alinhado ({alpha_20d:.1f}%)"
        is_out = False
    else:
        status = "Atrasado vs Ibov"
        badge = f"🔴 Fraco ({alpha_20d:.1f}%)"
        is_out = False

    return {
        "alpha_20d": alpha_20d,
        "alpha_60d": alpha_60d,
        "ret_asset_20": round(ret_asset_20, 1),
        "ret_bench_20": round(ret_bench_20, 1),
        "rs_status": status,
        "rs_badge": badge,
        "is_outperforming": is_out
    }

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

    # Volume & Liquidez Financeira
    if 'Volume' in res.columns:
        res['Volume_MA20'] = calculate_sma(res['Volume'], 20)
        res['Volume_Ratio'] = res['Volume'] / res['Volume_MA20'].replace(0, np.nan)
        res['Volume_Ratio'] = res['Volume_Ratio'].fillna(1.0)
        # Volume Financeiro Diário (Preço * Quantidade)
        res['Financial_Volume'] = res['Close'] * res['Volume']
        res['Financial_Volume_MA20'] = calculate_sma(res['Financial_Volume'], 20)
    else:
        res['Volume_MA20'] = np.nan
        res['Volume_Ratio'] = 1.0
        res['Financial_Volume'] = 0.0
        res['Financial_Volume_MA20'] = 0.0

    # Padrões de Candle
    patterns = detect_candlestick_patterns(res)
    res['Pattern_Hammer'] = patterns['Hammer']
    res['Pattern_Engulfing'] = patterns['Bullish_Engulfing']
    res['Pattern_InsideBar'] = patterns['Inside_Bar']

    # Setup 9.1 de Larry Williams
    ema9 = res['EMA9']
    ema9_shift1 = ema9.shift(1)
    ema9_shift2 = ema9.shift(2)
    res['Setup_9_1'] = (ema9 > ema9_shift1) & (ema9_shift1 <= ema9_shift2) & (res['Close'] > ema9)

    return res
