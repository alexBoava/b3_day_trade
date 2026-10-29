import datetime
from sqlalchemy import (
    Column, Integer, String, Float, BigInteger, Date, DateTime,
    Boolean, UniqueConstraint, Index, Text
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Ticker(Base):
    __tablename__ = "tickers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=True)
    sector = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    def __repr__(self):
        return f"<Ticker(symbol='{self.symbol}', active={self.is_active})>"

class DailyCandle(Base):
    __tablename__ = "daily_candles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker_symbol = Column(String(20), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    adj_close = Column(Float, nullable=True)
    volume = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("ticker_symbol", "date", name="uq_ticker_date"),
        Index("idx_candle_ticker_date", "ticker_symbol", "date"),
    )

    def __repr__(self):
        return f"<DailyCandle({self.ticker_symbol}, {self.date}, C={self.close})>"

class SwingSignal(Base):
    __tablename__ = "swing_signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker_symbol = Column(String(20), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    strategy = Column(String(80), nullable=False)
    signal_type = Column(String(30), nullable=False)  # 'COMPRA FORTE', 'COMPRA', 'ATENÇÃO'
    entry_price = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=False)
    target_1 = Column(Float, nullable=False)
    target_2 = Column(Float, nullable=False)
    risk_reward = Column(Float, nullable=False)
    details = Column(Text, nullable=True)
    status = Column(String(20), default="OPEN")  # OPEN, TARGET_1, TARGET_2, STOPPED, CLOSED
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    __table_args__ = (
        Index("idx_signal_date", "date"),
        Index("idx_signal_ticker_date", "ticker_symbol", "date"),
    )

    def __repr__(self):
        return f"<SwingSignal({self.ticker_symbol}, {self.date}, {self.signal_type})>"
