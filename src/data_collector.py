import datetime
import logging
from typing import List, Optional, Callable, Dict, Any, Tuple
import pandas as pd
import yfinance as yf
from sqlalchemy import func

from database.connection import get_db_session, init_db
from database.models import Ticker, DailyCandle, SwingSignal
from src.default_tickers import DEFAULT_TICKERS
from src.indicators import calculate_all_indicators
from src.strategies import analyze_swing_trade_signals

logger = logging.getLogger(__name__)

def ensure_initial_tickers():
    """Garante que a lista inicial padrão de tickers da B3 esteja cadastrada."""
    init_db()
    with get_db_session() as session:
        count = session.query(Ticker).count()
        if count == 0:
            for item in DEFAULT_TICKERS:
                t = Ticker(
                    symbol=item["symbol"],
                    name=item["name"],
                    sector=item["sector"],
                    is_active=True
                )
                session.add(t)
            session.commit()
            logger.info(f"Cadastrados {len(DEFAULT_TICKERS)} tickers padrão.")

def get_active_tickers() -> List[Dict[str, str]]:
    """Retorna a lista de tickers ativos cadastrados no banco."""
    ensure_initial_tickers()
    with get_db_session() as session:
        tickers = session.query(Ticker).filter(Ticker.is_active == True).all()
        return [{"symbol": t.symbol, "name": t.name or t.symbol, "sector": t.sector or "Geral"} for t in tickers]

def add_ticker(symbol: str, name: str = "", sector: str = "") -> bool:
    """Adiciona um novo ticker ao monitoramento."""
    symbol = symbol.strip().upper()
    if not symbol.endswith(".SA"):
        symbol = f"{symbol}.SA"

    with get_db_session() as session:
        existing = session.query(Ticker).filter(Ticker.symbol == symbol).first()
        if existing:
            existing.is_active = True
            if name:
                existing.name = name
            if sector:
                existing.sector = sector
        else:
            new_ticker = Ticker(symbol=symbol, name=name or symbol, sector=sector or "Outros", is_active=True)
            session.add(new_ticker)
        session.commit()
    return True

def remove_ticker(symbol: str) -> bool:
    """Desativa ou remove um ticker da lista ativa."""
    with get_db_session() as session:
        t = session.query(Ticker).filter(Ticker.symbol == symbol).first()
        if t:
            t.is_active = False
            session.commit()
            return True
    return False

def clean_yfinance_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Trata MultiIndex gerado por versões recentes do yfinance."""
    if df.empty:
        return df

    if isinstance(df.columns, pd.MultiIndex):
        # Se nível 0 são os tipos ('Open', 'High', etc.) e nível 1 os tickers:
        df.columns = df.columns.get_level_values(0)

    # Converter índice para datetime puro sem timezone para evitar conflitos com SQLite/Postgres
    if hasattr(df.index, 'tz_localize') and df.index.tz is not None:
        df.index = df.index.tz_convert(None)
    elif hasattr(df.index, 'tz') and df.index.tz is not None:
        df.index = df.index.tz_localize(None)

    # Padronizar nomes de colunas
    col_mapping = {col: col.capitalize() for col in df.columns}
    df = df.rename(columns=col_mapping)

    required = ['Open', 'High', 'Low', 'Close', 'Volume']
    for col in required:
        if col not in df.columns:
            logger.warning(f"Coluna esperada {col} não encontrada no dataframe do yfinance.")
            return pd.DataFrame()

    return df

def fetch_stock_candles(ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    """
    Baixa os dados históricos de um ticker via yfinance e retorna DataFrame limpo.
    """
    try:
        data = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=False)
        df = clean_yfinance_dataframe(data)
        return df
    except Exception as e:
        logger.error(f"Erro ao baixar dados para {ticker}: {e}")
        return pd.DataFrame()

def get_latest_candle_date(ticker: str) -> Optional[datetime.date]:
    """Retorna a data mais recente armazenada no banco para o ticker."""
    with get_db_session() as session:
        latest = session.query(func.max(DailyCandle.date)).filter(DailyCandle.ticker_symbol == ticker).scalar()
        return latest

def get_candle_count(ticker: str) -> int:
    """Retorna a quantidade de candles já salvos no banco para o ticker."""
    with get_db_session() as session:
        count = session.query(func.count(DailyCandle.id)).filter(DailyCandle.ticker_symbol == ticker).scalar()
        return count or 0

def is_trading_day_up_to_date(latest_date: Optional[datetime.date]) -> bool:
    """
    Avalia se o último candle no banco já corresponde ao pregão fechado mais recente da B3.
    Evita chamadas de rede desnecessárias.
    """
    if not latest_date:
        return False

    today = datetime.date.today()
    if latest_date >= today:
        return True

    weekday = today.weekday()  # 0=Segunda, 4=Sexta, 5=Sábado, 6=Domingo
    now = datetime.datetime.now()

    # Final de semana: se o último candle for da sexta-feira anterior, está 100% atualizado
    if weekday == 5 and latest_date >= (today - datetime.timedelta(days=1)):
        return True
    if weekday == 6 and latest_date >= (today - datetime.timedelta(days=2)):
        return True

    # Segunda-feira antes do fechamento do pregão (18h)
    if weekday == 0 and now.hour < 18 and latest_date >= (today - datetime.timedelta(days=3)):
        return True

    # Terça a Sexta antes das 18h: se tiver o dia de ontem, está atualizado com o último pregão completo
    if weekday in [1, 2, 3, 4] and now.hour < 18 and latest_date >= (today - datetime.timedelta(days=1)):
        return True

    return False

def save_candles_to_db(ticker: str, df: pd.DataFrame) -> Tuple[int, int]:
    """
    Salva ou atualiza candles no banco de dados.
    - Insere novos candles (evitando duplicatas).
    - Atualiza candles recentes (últimos 3 dias) para consolidar o preço de fechamento pós-pregão.
    Retorna tupla: (inseridos, atualizados).
    """
    if df.empty:
        return (0, 0)

    inserted_count = 0
    updated_count = 0
    today = datetime.date.today()
    recent_threshold = today - datetime.timedelta(days=3)

    with get_db_session() as session:
        # Obter todas as datas já gravadas para o ticker
        existing_records = {
            r.date: r for r in session.query(DailyCandle).filter(DailyCandle.ticker_symbol == ticker).all()
        }

        for idx, row in df.iterrows():
            c_date = idx.date() if hasattr(idx, 'date') else idx

            if c_date in existing_records:
                # Se o candle já existe e for recente, atualiza preços e volume de fechamento
                if c_date >= recent_threshold:
                    candle = existing_records[c_date]
                    candle.open = float(row['Open'])
                    candle.high = float(row['High'])
                    candle.low = float(row['Low'])
                    candle.close = float(row['Close'])
                    candle.adj_close = float(row.get('Adj close', row['Close']))
                    candle.volume = int(row['Volume']) if not pd.isna(row['Volume']) else 0
                    updated_count += 1
            else:
                # Inserção de novo candle
                try:
                    candle = DailyCandle(
                        ticker_symbol=ticker,
                        date=c_date,
                        open=float(row['Open']),
                        high=float(row['High']),
                        low=float(row['Low']),
                        close=float(row['Close']),
                        adj_close=float(row.get('Adj close', row['Close'])),
                        volume=int(row['Volume']) if not pd.isna(row['Volume']) else 0
                    )
                    session.add(candle)
                    existing_records[c_date] = candle
                    inserted_count += 1
                except Exception as e:
                    logger.debug(f"Erro ao inserir candle de {ticker} em {c_date}: {e}")

        session.commit()

    return (inserted_count, updated_count)

def load_candles_from_db(ticker: str, limit: int = 300) -> pd.DataFrame:
    """Carrega os últimos candles salvos no banco de dados para um ticker."""
    with get_db_session() as session:
        records = (
            session.query(DailyCandle)
            .filter(DailyCandle.ticker_symbol == ticker)
            .order_by(DailyCandle.date.desc())
            .limit(limit)
            .all()
        )

        if not records:
            return pd.DataFrame()

        records.reverse()  # Ordenar cronologicamente
        data = [{
            "Date": r.date,
            "Open": r.open,
            "High": r.high,
            "Low": r.low,
            "Close": r.close,
            "Adj Close": r.adj_close or r.close,
            "Volume": r.volume or 0
        } for r in records]

        df = pd.DataFrame(data)
        df['Date'] = pd.to_datetime(df['Date'])
        df.set_index('Date', inplace=True)
        return df

def get_or_sync_ticker_candles(ticker: str, force_download: bool = False, min_candles: int = 120) -> Tuple[pd.DataFrame, str]:
    """
    Estratégia Cache-First Inteligente:
    1. Se o banco já possui histórico e está em dia com a B3 -> Retorna direto do banco (0ms de rede).
    2. Se faltam poucos dias (ex: até 20 dias) -> Baixa APENAS os dias recentes (incremental).
    3. Se o banco está vazio ou com poucos candles ou force_download=True -> Baixa histórico completo (1 ano).
    Retorna tupla: (df_candles, origem_str).
    """
    count = get_candle_count(ticker)
    latest_date = get_latest_candle_date(ticker)
    today = datetime.date.today()

    # 1. Se já tem histórico e o pregão mais recente já está no banco, não faz download
    if not force_download and count >= min_candles and is_trading_day_up_to_date(latest_date):
        df_cached = load_candles_from_db(ticker, limit=min_candles * 2)
        if not df_cached.empty and len(df_cached) >= 20:
            return df_cached, "banco (cache local atualizado)"

    # 2. Se temos histórico razoável, mas faltam alguns dias recentes (atualização incremental)
    if not force_download and count >= min_candles and latest_date:
        days_gap = (today - latest_date).days
        if days_gap <= 20:
            logger.info(f"Atualização incremental para {ticker} ({days_gap} dias atrás)...")
            delta_df = fetch_stock_candles(ticker, period="1mo", interval="1d")
            if not delta_df.empty:
                save_candles_to_db(ticker, delta_df)
                df_updated = load_candles_from_db(ticker, limit=min_candles * 2)
                return df_updated, "banco (após sincronização incremental)"

    # 3. Se não tem dados suficientes no banco ou solicitou force_download
    logger.info(f"Baixando histórico completo de 1 ano para {ticker}...")
    fresh_df = fetch_stock_candles(ticker, period="1y", interval="1d")
    if not fresh_df.empty:
        save_candles_to_db(ticker, fresh_df)
        df_full = load_candles_from_db(ticker, limit=300)
        return df_full, "yfinance (download inicial gravado no banco)"

    # Fallback se a internet falhou: tenta o que estiver no banco
    df_fallback = load_candles_from_db(ticker, limit=300)
    return df_fallback, "banco (offline / fallback)"

def sync_ticker_data(ticker: str, force_download: bool = False) -> Optional[Dict[str, Any]]:
    """
    Sincroniza os dados de um ticker utilizando a estratégia de cache em banco.
    Calcula indicadores e avalia os sinais de Swing Trade.
    """
    df, origem = get_or_sync_ticker_candles(ticker, force_download=force_download)

    if df.empty or len(df) < 20:
        return None

    # Adiciona indicadores
    df_with_ind = calculate_all_indicators(df)
    signal = analyze_swing_trade_signals(df_with_ind, ticker)

    if signal:
        signal["data_source"] = origem
        # Se gerou um sinal relevante de compra ou observação, salva no histórico
        if signal["signal"] in ["COMPRA FORTE", "COMPRA", "ATENÇÃO (Aguardando Gatilho)"]:
            save_signal_to_db(signal)

    return signal

def save_signal_to_db(signal: Dict[str, Any]):
    """Registra um sinal gerado no banco de dados se ainda não registrado no mesmo dia."""
    try:
        with get_db_session() as session:
            sig_date = signal["date"]
            if isinstance(sig_date, str):
                sig_date = datetime.datetime.strptime(sig_date, "%Y-%m-%d").date()

            existing = (
                session.query(SwingSignal)
                .filter(
                    SwingSignal.ticker_symbol == signal["ticker"],
                    SwingSignal.date == sig_date,
                    SwingSignal.strategy == signal["strategy"]
                )
                .first()
            )

            if not existing:
                s = SwingSignal(
                    ticker_symbol=signal["ticker"],
                    date=sig_date,
                    strategy=signal["strategy"],
                    signal_type=signal["signal"],
                    entry_price=signal["entry_price"],
                    stop_loss=signal["stop_loss"],
                    target_1=signal["target_1"],
                    target_2=signal["target_2"],
                    risk_reward=signal["risk_reward"],
                    details=signal["reason"],
                    status="OPEN"
                )
                session.add(s)
                session.commit()
    except Exception as e:
        logger.error(f"Erro ao salvar sinal no banco: {e}")

def sync_all_tickers(
    force_download: bool = False,
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> List[Dict[str, Any]]:
    """
    Sincroniza todos os ativos ativos e retorna lista consolidada de análises.
    Prioriza o banco de dados e só baixa o que realmente estiver desatualizado.
    """
    tickers = get_active_tickers()
    total = len(tickers)
    results = []

    for i, t in enumerate(tickers):
        symbol = t["symbol"]
        if progress_callback:
            progress_callback((i + 1) / total, f"Processando {symbol} ({t['name']})...")

        analysis = sync_ticker_data(symbol, force_download=force_download)
        if analysis:
            analysis["name"] = t["name"]
            analysis["sector"] = t["sector"]
            results.append(analysis)

    return results

def get_database_stats() -> Dict[str, Any]:
    """Retorna estatísticas do banco de dados (total de candles, ativos e última data)."""
    with get_db_session() as session:
        total_candles = session.query(func.count(DailyCandle.id)).scalar() or 0
        total_tickers = session.query(func.count(Ticker.id)).filter(Ticker.is_active == True).scalar() or 0
        total_signals = session.query(func.count(SwingSignal.id)).scalar() or 0
        latest_date = session.query(func.max(DailyCandle.date)).scalar()
        return {
            "total_candles": total_candles,
            "total_tickers": total_tickers,
            "total_signals": total_signals,
            "latest_candle_date": latest_date
        }
