import datetime
from typing import Dict, Any, Optional
import pandas as pd
import numpy as np

from src.indicators import detect_rsi_bullish_divergence, calculate_relative_strength

def evaluate_trend(row: pd.Series) -> Dict[str, Any]:
    """Classifica a tendência de médio/longo prazo do ativo com base nas médias."""
    c = row['Close']
    ema20 = row.get('EMA20', np.nan)
    ema50 = row.get('EMA50', np.nan)
    ema200 = row.get('EMA200', np.nan)

    if pd.isna(ema50) or pd.isna(ema20):
        return {"trend": "Indefinida", "color": "gray", "score": 0}

    if not pd.isna(ema200) and (c > ema20 > ema50 > ema200):
        return {"trend": "Forte Alta", "color": "#00C853", "score": 3}
    elif c > ema50:
        return {"trend": "Alta", "color": "#26A69A", "score": 2}
    elif not pd.isna(ema200) and (c < ema20 < ema50 < ema200):
        return {"trend": "Forte Baixa", "color": "#D50000", "score": -3}
    elif c < ema50:
        return {"trend": "Baixa", "color": "#EF5350", "score": -2}
    else:
        return {"trend": "Lateral / Consolidação", "color": "#FFA726", "score": 0}

def analyze_swing_trade_signals(
    df: pd.DataFrame,
    ticker: str,
    df_benchmark: Optional[pd.DataFrame] = None,
    calendar_info: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """
    Motor de Estratégias de Swing Trade:
    - Identifica setups de alta probabilidade:
        1. Divergência de Alta no IFR (Reversão em fundo com stop curto)
        2. Recuo na Tendência (Trend Pullback)
        3. Setup 9.1 de Larry Williams
        4. Sobrevenda em Suporte (IFR < 38)
        5. Rompimento de Resistência com Volume (Breakout)
    - Incorpora Força Relativa contra o Ibovespa (Alpha 20d e 60d).
    - Valida Liquidez Financeira e emite Alertas de Calendário (Balanço / Proventos).
    """
    if df.empty or len(df) < 25:
        return None

    last = df.iloc[-1]
    prev = df.iloc[-2]

    c = float(last['Close'])
    h = float(last['High'])
    l = float(last['Low'])
    o = float(last['Open'])

    rsi = float(last['RSI']) if not pd.isna(last['RSI']) else 50.0
    ema20 = float(last['EMA20']) if not pd.isna(last['EMA20']) else c
    ema50 = float(last['EMA50']) if not pd.isna(last['EMA50']) else c
    ema200 = float(last['EMA200']) if not pd.isna(last['EMA200']) else c
    atr = float(last['ATR']) if not pd.isna(last['ATR']) and last['ATR'] > 0 else (c * 0.02)
    bb_lower = float(last['BB_Lower']) if not pd.isna(last['BB_Lower']) else c * 0.95
    vol_ratio = float(last['Volume_Ratio']) if not pd.isna(last['Volume_Ratio']) else 1.0

    # Liquidez Financeira Média (20 dias em R$)
    fin_vol_ma20 = float(last.get('Financial_Volume_MA20', 0.0))
    is_liquid = fin_vol_ma20 >= 4_500_000.0  # R$ 4.5M/dia
    liquidity_badge = f"R$ {fin_vol_ma20 / 1e6:.1f}M/dia" if fin_vol_ma20 > 0 else "N/A"

    # Força Relativa contra o Ibovespa
    rs_data = calculate_relative_strength(df, df_benchmark)
    alpha_20d = rs_data['alpha_20d']
    rs_badge = rs_data['rs_badge']

    # Divergência de Alta no IFR
    divergence_data = detect_rsi_bullish_divergence(df, lookback=25)

    # Tendência
    trend_info = evaluate_trend(last)
    is_up_trend = trend_info['score'] >= 1
    recent_min = float(df['Low'].tail(5).min())
    recent_max = float(df['High'].tail(20).iloc[:-1].max()) if len(df) >= 21 else float(df['High'].max())

    sinal_tipo = "NEUTRO"
    estrategia = "Sem Gatilho"
    motivo = []
    prioridade = 0  # 3: Forte, 2: Compra, 1: Atenção, 0: Neutro

    custom_stop = None

    # 1. SETUP DE ELITE: Divergência de Alta no IFR (Reversão com stop curto)
    if divergence_data.get('detected', False):
        sinal_tipo = "COMPRA FORTE" if rs_data['is_outperforming'] else "COMPRA"
        estrategia = "Divergência de Alta (IFR)"
        prioridade = 3 if rs_data['is_outperforming'] else 2
        motivo.append(divergence_data['reason'])
        # Stop posicionado logo abaixo do fundo da divergência
        custom_stop = divergence_data['low_recent'] * 0.992

    # 2. SETUP: Recuo na Tendência (Trend Pullback)
    elif is_up_trend and (abs(c - ema20) / ema20 <= 0.035 or abs(c - ema50) / ema50 <= 0.035 or l <= ema20 <= h) and (35 <= rsi <= 55) and (c >= o or c > float(prev['Close'])):
        sinal_tipo = "COMPRA FORTE" if (bool(last.get('Pattern_Hammer', False)) or bool(last.get('Pattern_Engulfing', False)) or rs_data['is_outperforming']) else "COMPRA"
        estrategia = "Recuo na Tendência (Pullback)"
        prioridade = 3 if "COMPRA FORTE" in sinal_tipo else 2
        motivo.append(f"Ativo em tendência de {trend_info['trend']}, recuou até a média com IFR equilibrado ({rsi:.1f}).")
        if bool(last.get('Pattern_Hammer', False)):
            motivo.append("Candle Martelo formado na média de suporte.")

    # 3. SETUP: Setup 9.1 de Larry Williams (Virada da Média 9 para cima)
    elif bool(last.get('Setup_9_1', False)) and (c > ema50 or c > ema200):
        sinal_tipo = "COMPRA"
        estrategia = "Setup 9.1 (Larry Williams)"
        prioridade = 2
        motivo.append(f"EMA 9 virou para cima após recuo. Gatilho no rompimento de R$ {h:.2f}.")

    # 4. SETUP: Rompimento de Resistência com Volume (Breakout)
    elif (c > recent_max) and (vol_ratio >= 1.25) and is_up_trend:
        sinal_tipo = "COMPRA FORTE" if vol_ratio >= 1.5 and rs_data['is_outperforming'] else "COMPRA"
        estrategia = "Rompimento de Resistência (Breakout)"
        prioridade = 3 if "FORTE" in sinal_tipo else 2
        motivo.append(f"Rompimento da máxima de 20 pregões (R$ {recent_max:.2f}) com volume {vol_ratio:.1f}x acima da média.")

    # 5. SETUP: Sobrevenda com Gatilho (IFR < 38)
    elif rsi <= 38 and (c >= o or bool(last.get('Pattern_Hammer', False)) or c > bb_lower):
        sinal_tipo = "COMPRA" if c > o else "ATENÇÃO (Rastrear)"
        estrategia = "Sobrevenda em Suporte (IFR)"
        prioridade = 2 if c > o else 1
        motivo.append(f"IFR em sobrevenda ({rsi:.1f}) próximo ao fundo. Potencial repique comprador.")

    # Observação / Neutro
    elif is_up_trend and (35 <= rsi <= 45):
        sinal_tipo = "ATENÇÃO (Aguardando Gatilho)"
        estrategia = "Correção em Andamento"
        prioridade = 1
        motivo.append(f"Ativo corrigindo na alta (IFR {rsi:.1f}). Aguardar reação de candle.")

    elif rsi > 70:
        sinal_tipo = "ALERTA (Sobrecomprado)"
        estrategia = "IFR Esticado (> 70)"
        prioridade = 0
        motivo.append(f"IFR esticado ({rsi:.1f}). Risco elevado para novas compras.")
    else:
        sinal_tipo = "NEUTRO"
        estrategia = "Sem Sinal Claro"
        prioridade = 0
        motivo.append("Preço oscilando sem configuração clara de entrada no momento.")

    # Anotações de Força Relativa
    if rs_data['is_outperforming']:
        motivo.append(f"Força Relativa: {rs_data['rs_badge']} frente ao Ibovespa.")

    # Alertas de Calendário (Balanço Trimestral & Dividendos)
    calendar_alert = "Sem balanço nos próx. 7 dias"
    has_earnings_risk = False
    if calendar_info:
        days_to_earnings = calendar_info.get("days_to_earnings")
        earnings_date = calendar_info.get("earnings_date")
        if days_to_earnings is not None and 0 <= days_to_earnings <= 7:
            has_earnings_risk = True
            date_str = earnings_date.strftime('%d/%m') if hasattr(earnings_date, 'strftime') else str(earnings_date)
            calendar_alert = f"⚠️ Balanço em {days_to_earnings}d ({date_str})"
            motivo.append(f"ALERTA DE RISCO: Balanço em {days_to_earnings} dias. Risco elevado de gap na abertura!")

    # Alerta de Liquidez se baixa
    if not is_liquid and fin_vol_ma20 > 0:
        motivo.append(f"Atenção à Liquidez: Volume diário ({liquidity_badge}) abaixo de R$ 5M.")

    # Cálculo da Gestão de Risco e Projeção de Alvos
    preco_entrada = c
    if custom_stop:
        stop_loss = custom_stop
    else:
        stop_tecnico_minima = recent_min * 0.994
        stop_atr = preco_entrada - (1.5 * atr)
        stop_loss = max(stop_tecnico_minima, stop_atr)

    dist_stop_pct = (preco_entrada - stop_loss) / preco_entrada
    if dist_stop_pct < 0.018:
        stop_loss = preco_entrada * 0.982
    elif dist_stop_pct > 0.09:
        stop_loss = preco_entrada * 0.91

    risco_unitario = max(preco_entrada - stop_loss, 0.05)
    alvo_1 = round(preco_entrada + (1.5 * risco_unitario), 2)
    alvo_2 = round(preco_entrada + (2.5 * risco_unitario), 2)
    stop_loss = round(stop_loss, 2)
    preco_entrada = round(preco_entrada, 2)

    risk_reward = round((alvo_2 - preco_entrada) / (preco_entrada - stop_loss), 2) if (preco_entrada - stop_loss) > 0 else 2.5

    data_candle = last.name if hasattr(last, 'name') else datetime.date.today()
    if hasattr(data_candle, 'date'):
        data_candle = data_candle.date()

    return {
        "ticker": ticker,
        "date": data_candle,
        "close": c,
        "high": h,
        "low": l,
        "rsi": round(rsi, 1),
        "trend": trend_info['trend'],
        "trend_color": trend_info['color'],
        "signal": sinal_tipo,
        "strategy": estrategia,
        "priority": prioridade,
        "entry_price": preco_entrada,
        "stop_loss": stop_loss,
        "stop_loss_pct": round(((stop_loss - preco_entrada) / preco_entrada) * 100, 2),
        "target_1": alvo_1,
        "target_1_pct": round(((alvo_1 - preco_entrada) / preco_entrada) * 100, 2),
        "target_2": alvo_2,
        "target_2_pct": round(((alvo_2 - preco_entrada) / preco_entrada) * 100, 2),
        "risk_reward": risk_reward,
        "volume_ratio": round(vol_ratio, 2),
        "alpha_20d": alpha_20d,
        "alpha_60d": rs_data['alpha_60d'],
        "rs_badge": rs_badge,
        "is_outperforming": rs_data['is_outperforming'],
        "financial_volume_ma20": fin_vol_ma20,
        "liquidity_badge": liquidity_badge,
        "is_liquid": is_liquid,
        "calendar_alert": calendar_alert,
        "has_earnings_risk": has_earnings_risk,
        "reason": " | ".join(motivo),
        "ema20": round(ema20, 2),
        "ema50": round(ema50, 2),
        "ema200": round(ema200, 2)
    }
