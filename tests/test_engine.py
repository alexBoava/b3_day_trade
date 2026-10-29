import os
import sys
import datetime

# Adicionar diretório raiz ao PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import numpy as np

from src.indicators import calculate_all_indicators
from src.strategies import analyze_swing_trade_signals
from src.risk_manager import calculate_position_size
from database.connection import init_db, check_db_connection

def test_indicators_and_signals():
    print("1. Testando conexão com banco e criação de tabelas...")
    init_db()
    ok, db_type = check_db_connection()
    print(f"   -> Banco ativo: {db_type} (OK={ok})")
    assert ok, "Falha na conexão com banco de dados"

    print("2. Gerando série temporal simulada de 100 dias...")
    dates = pd.date_range(end=datetime.date.today(), periods=100, freq='D')
    np.random.seed(42)
    base_price = 30.0 + np.cumsum(np.random.randn(100) * 0.5)

    df = pd.DataFrame({
        'Open': base_price + np.random.randn(100) * 0.2,
        'High': base_price + np.abs(np.random.randn(100) * 0.6),
        'Low': base_price - np.abs(np.random.randn(100) * 0.6),
        'Close': base_price,
        'Volume': np.random.randint(1000000, 5000000, size=100)
    }, index=dates)

    print("3. Calculando indicadores técnicos...")
    df_ind = calculate_all_indicators(df)
    for col in ['EMA9', 'EMA20', 'EMA50', 'EMA200', 'RSI', 'MACD', 'BB_Upper', 'ATR']:
        assert col in df_ind.columns, f"Coluna {col} ausente!"
    print(f"   -> Indicadores calculados com sucesso. Último RSI: {df_ind['RSI'].iloc[-1]:.2f}")

    print("4. Analisando sinais de Swing Trade...")
    signal = analyze_swing_trade_signals(df_ind, "PETR4.SA")
    assert signal is not None, "Falha ao gerar análise de sinais"
    print(f"   -> Sinal gerado: {signal['signal']} | Estratégia: {signal['strategy']}")
    print(f"   -> Entrada: R$ {signal['entry_price']} | Stop: R$ {signal['stop_loss']} | Alvo 2: R$ {signal['target_2']}")

    print("5. Testando dimensionamento de risco...")
    risco = calculate_position_size(
        capital_total=25000.0,
        risco_por_operacao_pct=1.5,
        preco_entrada=signal['entry_price'],
        preco_stop=signal['stop_loss'],
        alvo_1=signal['target_1'],
        alvo_2=signal['target_2']
    )
    assert "qtd_acoes" in risco, "Falha no cálculo de risco"
    print(f"   -> Quantidade calculada: {risco['qtd_acoes']} ações | Capital alocado: R$ {risco['capital_alocado']}")
    print("Todos os testes passaram com 100% de sucesso!")

if __name__ == "__main__":
    test_indicators_and_signals()
