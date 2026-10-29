import time
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.data_collector import get_or_sync_ticker_candles, get_database_stats

def test_cache():
    print("--- Teste de Persistência e Evitação de Downloads ---")

    # 1ª chamada: se não estiver no banco, baixa e grava
    t0 = time.time()
    df1, orig1 = get_or_sync_ticker_candles("VALE3.SA")
    t1 = time.time()
    print(f"1ª Chamada (VALE3.SA): {orig1} em {t1 - t0:.2f}s | Candles: {len(df1)}")

    # 2ª chamada: DEVE vir 100% do banco, sem download pela rede
    t2 = time.time()
    df2, orig2 = get_or_sync_ticker_candles("VALE3.SA")
    t3 = time.time()
    print(f"2ª Chamada (VALE3.SA): {orig2} em {t3 - t2:.4f}s | Candles: {len(df2)}")

    stats = get_database_stats()
    print(f"Total de candles persistidos no banco: {stats['total_candles']}")
    print(f"Última data gravada no banco: {stats['latest_candle_date']}")

    assert "banco" in orig2, "A segunda chamada deveria vir diretamente do banco de dados!"
    assert (t3 - t2) < 0.2, "O carregamento do banco deve ser instantâneo (< 0.2s)!"
    print("Sucesso! Os dados estão no banco e a reutilização evitou download pela rede.")

if __name__ == "__main__":
    test_cache()
