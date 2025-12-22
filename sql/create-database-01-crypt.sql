-- Crypto monitor schema (PostgreSQL)

CREATE TABLE IF NOT EXISTS klines (
    symbol TEXT NOT NULL,
    open_time BIGINT NOT NULL,
    close_time BIGINT NOT NULL,
    open DOUBLE PRECISION NOT NULL,
    high DOUBLE PRECISION NOT NULL,
    low DOUBLE PRECISION NOT NULL,
    close DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (symbol, open_time)
);

CREATE TABLE IF NOT EXISTS window_stats (
    symbol TEXT NOT NULL,
    window_end BIGINT NOT NULL,
    change_close DOUBLE PRECISION NOT NULL,
    change_low DOUBLE PRECISION NOT NULL,
    change_high DOUBLE PRECISION NOT NULL,
    length INTEGER NOT NULL,
    PRIMARY KEY (symbol, window_end)
);

CREATE TABLE IF NOT EXISTS alerts (
    id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    magnitude DOUBLE PRECISION NOT NULL,
    ts BIGINT NOT NULL,
    reference_open DOUBLE PRECISION NOT NULL,
    reference_close DOUBLE PRECISION NOT NULL,
    reference_low DOUBLE PRECISION NOT NULL,
    reference_high DOUBLE PRECISION NOT NULL,
    reference_peak_ts BIGINT,
    reference_current_ts BIGINT,
    drop_from_peak DOUBLE PRECISION,
    anchor_type TEXT,
    anchor_price DOUBLE PRECISION,
    anchor_ts BIGINT,
    anchor_pct_from_open DOUBLE PRECISION,
    current_pct_from_open DOUBLE PRECISION,
    move_from_anchor DOUBLE PRECISION
);
