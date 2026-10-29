import datetime
from typing import Dict, Any, Optional
import pandas as pd
import numpy as np

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

def analyze_swing_trade_signals(df: pd.DataFrame, ticker: str) -> Optional[Dict[str, Any]]:
    """
    Avalia os últimos candles do ativo e identifica se há sinal ou oportunidade
    de entrada para Swing Trade, além de projetar Stop Loss e Alvos.
    """
    if df.empty or len(df) < 25:
        return None

    last = df.iloc[-1]
    prev = df.iloc[-2]
    prev2 = df.iloc[-3] if len(df) >= 3 else prev

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
    bb_upper = float(last['BB_Upper']) if not pd.isna(last['BB_Upper']) else c * 1.05
    vol_ratio = float(last['Volume_Ratio']) if not pd.isna(last['Volume_Ratio']) else 1.0

    trend_info = evaluate_trend(last)
    is_up_trend = trend_info['score'] >= 1
    recent_min = float(df['Low'].tail(5).min())
    recent_max = float(df['High'].tail(20).iloc[:-1].max()) if len(df) >= 21 else float(df['High'].max())

    sinal_tipo = "NEUTRO"
    estrategia = "Sem Gatilho"
    motivo = []
    prioridade = 0  # 3: Forte, 2: Compra, 1: Atenção/Observar, 0: Neutro

    # 1. Estratégia: Recuo na Tendência (Trend Pullback) - A mais clássica e segura do Swing Trade
    dist_ema20 = abs(c - ema20) / ema20
    dist_ema50 = abs(c - ema50) / ema50
    perto_das_medias = (dist_ema20 <= 0.03) or (dist_ema50 <= 0.035) or (l <= ema20 <= h)

    if is_up_trend and perto_das_medias and (35 <= rsi <= 55) and (c >= o or c > float(prev['Close'])):
        sinal_tipo = "COMPRA"
        estrategia = "Recuo na Tendência (Pullback)"
        prioridade = 2
        motivo.append(f"Ativo em tendência de {trend_info['trend']}, recuou até a média (distância {dist_ema20*100:.1f}%) com IFR saudável ({rsi:.1f}).")
        if bool(last.get('Pattern_Hammer', False)) or bool(last.get('Pattern_Engulfing', False)):
            sinal_tipo = "COMPRA FORTE"
            prioridade = 3
            motivo.append("Candle de reversão (Martelo ou Engolfo) formado sobre a região de suporte/média.")

    # 2. Estratégia: Sobrevenda com Gatilho (RSI < 38)
    elif rsi <= 38 and (c >= o or bool(last.get('Pattern_Hammer', False)) or c > bb_lower):
        sinal_tipo = "COMPRA" if c > o else "ATENÇÃO (Rastrear)"
        estrategia = "Sobrevenda em Suporte (IFR)"
        prioridade = 2 if c > o else 1
        motivo.append(f"IFR em sobrevenda ({rsi:.1f}) próximo ao fundo/Banda Inferior. Potencial repique comprador.")

    # 3. Estratégia: Setup 9.1 de Larry Williams (Virada da Média 9 para cima)
    elif bool(last.get('Setup_9_1', False)) and (c > ema50 or c > ema200):
        sinal_tipo = "COMPRA"
        estrategia = "Setup 9.1 (Larry Williams)"
        prioridade = 2
        motivo.append(f"Média EMA 9 virou para cima após recuo, fechamento acima da média. Gatilho no rompimento de R$ {h:.2f}.")

    # 4. Estratégia: Rompimento de Resistência com Volume (Breakout)
    elif (c > recent_max) and (vol_ratio >= 1.2) and is_up_trend:
        sinal_tipo = "COMPRA FORTE" if vol_ratio >= 1.5 else "COMPRA"
        estrategia = "Rompimento de Resistência (Breakout)"
        prioridade = 3 if vol_ratio >= 1.5 else 2
        motivo.append(f"Rompimento da máxima de 20 períodos (R$ {recent_max:.2f}) com volume {vol_ratio:.1f}x acima da média.")

    # 5. Padrões de Observação / Atenção
    elif is_up_trend and (35 <= rsi <= 45):
        sinal_tipo = "ATENÇÃO (Aguardando Gatilho)"
        estrategia = "Correção em Andamento"
        prioridade = 1
        motivo.append(f"Ativo em correção na tendência de alta (IFR {rsi:.1f}). Aguardar candle de confirmação para compra.")

    elif rsi > 70:
        sinal_tipo = "ALERTA (Sobrecomprado)"
        estrategia = "IFR Esticado (> 70)"
        prioridade = 0
        motivo.append(f"IFR esticado ({rsi:.1f}). Risco elevado para novas compras no curto prazo.")

    else:
        sinal_tipo = "NEUTRO"
        estrategia = "Sem Sinal Claro"
        prioridade = 0
        motivo.append("Preço oscilando sem configuração clara de entrada no momento.")

    # Cálculo da Gestão de Risco e Projeção de Alvos
    preco_entrada = c
    # Stop loss técnico: mínima dos últimos 3 candles ou 1.5 ATR abaixo da entrada
    stop_tecnico_minima = recent_min * 0.995  # 0.5% abaixo do fundo recente
    stop_atr = preco_entrada - (1.5 * atr)
    stop_loss = max(stop_tecnico_minima, stop_atr)

    # Proteção: garantir que o stop loss não seja maior que 10% nem menor que 1.5% para Swing Trade
    dist_stop_pct = (preco_entrada - stop_loss) / preco_entrada
    if dist_stop_pct < 0.02:
        stop_loss = preco_entrada * 0.98  # Stop mínimo de 2%
    elif dist_stop_pct > 0.09:
        stop_loss = preco_entrada * 0.91  # Stop máximo de 9%

    risco_unitario = max(preco_entrada - stop_loss, 0.05)

    # Alvos baseados na simetria risco:retorno (1:1.5 e 1:2.5)
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
        "reason": " | ".join(motivo),
        "ema20": round(ema20, 2),
        "ema50": round(ema50, 2),
        "ema200": round(ema200, 2)
    }
