from datetime import date

from backend.app.instrument_master import InstrumentMaster


def test_commodity_rows_returns_nearest_active_mcx_future_per_root():
    master = InstrumentMaster()
    master.rows = [
        {"exch_seg": "MCX", "instrumenttype": "FUTCOM", "name": "GOLD", "symbol": "GOLD30DEC2026FUT", "expiry": "30DEC2026", "token": "gold-later"},
        {"exch_seg": "MCX", "instrumenttype": "FUTCOM", "name": "GOLD", "symbol": "GOLD30NOV2026FUT", "expiry": "30NOV2026", "token": "gold-front"},
        {"exch_seg": "MCX", "instrumenttype": "FUTCOM", "name": "GOLDM", "symbol": "GOLDM30NOV2026FUT", "expiry": "30NOV2026", "token": "goldm-front"},
        {"exch_seg": "MCX", "instrumenttype": "FUTCOM", "name": "CRUDEOIL", "symbol": "CRUDEOIL30SEP2026FUT", "expiry": "30SEP2026", "token": "crude-expired"},
        {"exch_seg": "NFO", "instrumenttype": "FUTCOM", "name": "GOLD", "symbol": "GOLD30NOV2026FUT", "expiry": "30NOV2026", "token": "not-mcx"},
        {"exch_seg": "MCX", "instrumenttype": "OPTFUT", "name": "GOLD", "symbol": "GOLD30NOV2026CE", "expiry": "30NOV2026", "token": "not-future"},
    ]

    rows = master.commodity_rows(as_of=date(2026, 10, 9))

    assert [row["token"] for row in rows] == ["gold-front", "goldm-front"]
