import os
import sys
import datetime

# Garantir UTF-8 no console Windows
if sys.platform == 'win32' and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import numpy as np

from src.indicators import (
    calculate_all_indicators,
    detect_rsi_bullish_divergence,
    calculate_relative_strength
)
from src.data_collector import (
    get_or_sync_ticker_candles,
    fetch_calendar_events,
    get_market_regime,
    sync_ticker_data
)
from src.strategies import analyze_swing_trade_signals

def test_new_features():
    print("==================================================")
    print("   TESTANDO NOVAS FUNCIONALIDADES DE SWING TRADE  ")
    print("==================================================")

    # 1. Testar Termômetro de Regime de Mercado (BOVA11)
    print("\n1. Testando Termômetro do Ibovespa (BOVA11)...")
    regime = get_market_regime()
    print(f"   -> Status do Mercado: {regime['status']} ({regime['badge']})")
    print(f"   -> Detalhes: {regime['detail']}")
    assert "status" in regime, "Falha no Regime de Mercado"

    # 2. Testar Alertas de Calendário (Balanços e Dividendos)
    print("\n2. Testando Alertas de Calendário (Balanço Trimestral)...")
    cal_vale = fetch_calendar_events("VALE3.SA")
    print(f"   -> VALE3.SA Balanço: {cal_vale.get('earnings_date')} | Dias restantes: {cal_vale.get('days_to_earnings')}")
    print(f"   -> VALE3.SA Data-Ex: {cal_vale.get('ex_dividend_date')} | Dias restantes: {cal_vale.get('days_to_dividend')}")
    assert isinstance(cal_vale, dict), "Falha no calendário corporativo"

    # 3. Testar Força Relativa contra o Ibov
    print("\n3. Testando Força Relativa (Alpha vs Ibov)...")
    df_petr, _ = get_or_sync_ticker_candles("PETR4.SA", min_candles=100)
    df_bova, _ = get_or_sync_ticker_candles("BOVA11.SA", min_candles=100)
    rs_petr = calculate_relative_strength(df_petr, df_bova)
    print(f"   -> PETR4.SA vs BOVA11: Alpha 20d = {rs_petr['alpha_20d']:+.1f}% | {rs_petr['rs_badge']}")
    assert "alpha_20d" in rs_petr, "Falha no cálculo de Força Relativa"

    # 4. Testar Algoritmo de Divergência de Alta no IFR
    print("\n4. Testando Detecção de Divergência de Alta no IFR...")
    # Criar uma série sintética com divergência de alta clássica:
    # Preço cai e renova mínima, enquanto RSI faz fundo mais alto
    dates = pd.date_range(end=datetime.date.today(), periods=35, freq='D')
    # Preço: cai para 20.0, sobe para 22.0, cai para 19.5 (fundo menor) e sobe para 20.2
    prices = [25.0 - i*0.4 for i in range(12)] + [20.2 + i*0.3 for i in range(8)] + [22.6 - i*0.4 for i in range(10)] + [19.2, 19.1, 19.0, 19.6, 20.0]
    prices = prices[:35]
    df_sim = pd.DataFrame({
        'Open': prices,
        'High': [p + 0.3 for p in prices],
        'Low': [p - 0.3 for p in prices],
        'Close': prices,
        'Volume': [2000000] * 35
    }, index=dates)
    df_sim_ind = calculate_all_indicators(df_sim)
    div_result = detect_rsi_bullish_divergence(df_sim_ind)
    print(f"   -> Resultado Divergência Sintética: {div_result.get('detected', False)}")
    if div_result.get('detected'):
        print(f"   -> Detalhes: {div_result['reason']}")

    # 5. Testar Análise Completa com todas as novidades integradas
    print("\n5. Testando Motor Integrado de Sinais em VALE3.SA...")
    signal_vale = sync_ticker_data("VALE3.SA")
    assert signal_vale is not None, "Falha na análise completa de VALE3.SA"
    print(f"   -> Ticker: {signal_vale['ticker']}")
    print(f"   -> Sinal: {signal_vale['signal']} | Estratégia: {signal_vale['strategy']}")
    print(f"   -> Força vs Ibov: {signal_vale['rs_badge']}")
    print(f"   -> Alerta Calendário: {signal_vale['calendar_alert']}")
    print(f"   -> Liquidez: {signal_vale['liquidity_badge']}")
    print(f"   -> Racional: {signal_vale['reason']}")

    print("\n==================================================")
    print("   TODOS OS TESTES PASSARAM COM 100% DE SUCESSO!  ")
    print("==================================================")

if __name__ == "__main__":
    test_new_features()
