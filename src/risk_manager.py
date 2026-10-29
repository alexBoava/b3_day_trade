import math
from typing import Dict, Any

def calculate_position_size(
    capital_total: float,
    risco_por_operacao_pct: float,
    preco_entrada: float,
    preco_stop: float,
    alvo_1: float,
    alvo_2: float,
    lote_padrao: bool = False
) -> Dict[str, Any]:
    """
    Calcula o dimensionamento correto de posição para Swing Trade com base no risco aceitável.
    Evita alavancagem excessiva e preserva o capital em caso de stop.
    """
    if preco_entrada <= 0 or preco_stop <= 0 or preco_entrada <= preco_stop:
        return {
            "error": "O preço de entrada deve ser maior que o preço de stop loss."
        }

    risco_financeiro_maximo = capital_total * (risco_por_operacao_pct / 100.0)
    risco_por_acao = preco_entrada - preco_stop

    # Quantidade máxima de ações com base no risco tolerado
    qtd_acoes = math.floor(risco_financeiro_maximo / risco_por_acao)

    # Ajuste de lote padrão (múltiplos de 100) caso solicitado
    if lote_padrao and qtd_acoes >= 100:
        qtd_acoes = (qtd_acoes // 100) * 100
    elif lote_padrao and qtd_acoes < 100:
        qtd_acoes = max(qtd_acoes, 1)

    if qtd_acoes == 0:
        qtd_acoes = 1

    capital_alocado = round(qtd_acoes * preco_entrada, 2)
    perda_maxima_real = round(qtd_acoes * risco_por_acao, 2)
    lucro_alvo_1 = round(qtd_acoes * (alvo_1 - preco_entrada), 2)
    lucro_alvo_2 = round(qtd_acoes * (alvo_2 - preco_entrada), 2)

    pct_capital_alocado = round((capital_alocado / capital_total) * 100.0, 1) if capital_total > 0 else 0.0

    return {
        "qtd_acoes": qtd_acoes,
        "capital_alocado": capital_alocado,
        "pct_capital_alocado": pct_capital_alocado,
        "risco_planejado_rs": round(risco_financeiro_maximo, 2),
        "perda_maxima_real_rs": perda_maxima_real,
        "lucro_alvo_1_rs": lucro_alvo_1,
        "retorno_alvo_1_pct": round(((alvo_1 - preco_entrada) / preco_entrada) * 100.0, 2),
        "lucro_alvo_2_rs": lucro_alvo_2,
        "retorno_alvo_2_pct": round(((alvo_2 - preco_entrada) / preco_entrada) * 100.0, 2),
        "risco_retorno_ratio": round((alvo_2 - preco_entrada) / risco_por_acao, 2) if risco_por_acao > 0 else 0
    }
