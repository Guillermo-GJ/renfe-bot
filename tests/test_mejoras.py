"""Tests for the station suggestions, date parsing, exact-time filter and calendar keyboards."""

from datetime import date, datetime, timedelta

import pytest

from calendar_kb import calendar_keyboard, describe_day, times_keyboard
from errors import InvalidTrainRideFilter, StationNotFound
from messages import user_messages as msg
from models import TrainRideFilter, TrainRideRecord
from storage import StationsStorage, normalize_name
from validators import validate_date, validate_station


@pytest.fixture(autouse=True)
def reset_stations_cache():
    """These tests load the real stations file: don't leave it cached for other tests' mocks."""
    StationsStorage.stations = None
    yield
    StationsStorage.stations = None


# ---------- Stations ----------

@pytest.mark.parametrize("raw, expected", [
    ("Córdoba", "CORDOBA"),
    ("zaragoza - delicias", "ZARAGOZA DELICIAS"),
    ("  A Coruña ", "A CORUNA"),
])
def test_normalize_name(raw, expected):
    assert normalize_name(raw) == expected


def test_station_without_accents_is_found():
    assert StationsStorage.get_station("CORDOBA").name == "CÓRDOBA"


def test_unknown_station_raises():
    with pytest.raises(StationNotFound):
        StationsStorage.get_station("ESTACION QUE NO EXISTE")


def test_partial_name_suggests_matching_stations():
    assert "ZARAGOZA-DELICIAS" in StationsStorage.find_station("delicias")


def test_typo_suggests_closest_station():
    assert "CÓRDOBA" in StationsStorage.find_station("Cordova")


def test_validate_station_returns_suggestions():
    result = validate_station("Cordova")
    assert not result
    assert "Córdoba" in result.suggestions


def test_validate_station_nothing_similar():
    result = validate_station("zzzzzz")
    assert not result
    assert result.error_message == msg["station_invalid"]


# ---------- Dates ----------

def test_date_in_natural_language():
    next_year = datetime.now().year + 1
    result = validate_date(f"14 de marzo de {next_year} a las 09:30")
    assert result.date == datetime(next_year, 3, 14, 9, 30)


def test_date_without_time_means_midnight():
    next_year = datetime.now().year + 1
    result = validate_date(f"14/03/{next_year}")
    assert result.date == datetime(next_year, 3, 14, 0, 0)


def test_past_date_is_rejected():
    result = validate_date("01/01/2020 10:00")
    assert not result
    assert result.error_message == msg["past_date"]


def test_only_time_is_rejected():
    assert not validate_date("09:30")


# ---------- Exact-time filter ----------

def _ride(hour, minute, available):
    departure = datetime(2030, 3, 14, hour, minute)
    return TrainRideRecord(origin="MADRID (TODAS)", destination="ZARAGOZA-DELICIAS",
                           departure_time=departure,
                           arrival_time=departure + timedelta(minutes=90), duration=90,
                           price=16.65, available=available, not_on_sale_yet=False,
                           train_type="MD", transfer_stations=[])


def _filter(exact):
    return TrainRideFilter(origin="MADRID (TODAS)", destination="ZARAGOZA-DELICIAS",
                           departure_date=datetime(2030, 3, 14, 9, 30), exact_time=exact)


def test_exact_time_ignores_other_trains():
    rides = [_ride(9, 30, False), _ride(12, 0, True)]
    assert _filter(exact=True).filter_rides(rides) == []


def test_exact_time_finds_the_train_when_free():
    rides = [_ride(9, 30, True), _ride(12, 0, True)]
    found = _filter(exact=True).filter_rides(rides)
    assert [r.departure_time.hour for r in found] == [9]


def test_exact_time_without_that_train_raises():
    with pytest.raises(InvalidTrainRideFilter):
        _filter(exact=True).filter_rides([_ride(10, 0, True)])


def test_from_time_returns_later_free_trains():
    rides = [_ride(9, 30, False), _ride(12, 0, True)]
    found = _filter(exact=False).filter_rides(rides)
    assert [r.departure_time.hour for r in found] == [12]


# ---------- Calendar keyboards ----------

def _texts(kb):
    return [button.text for row in kb.keyboard for button in row]


def _callbacks(kb):
    return [button.callback_data for row in kb.keyboard for button in row]


def test_calendar_blocks_past_days():
    kb = calendar_keyboard("ida", 2026, 11, today=date(2026, 11, 25))
    assert "ida:day:2026-11-24" not in _callbacks(kb)
    assert "ida:day:2026-11-25" in _callbacks(kb)
    assert "ida:day:2026-11-30" in _callbacks(kb)


def test_calendar_cannot_go_before_current_month():
    kb = calendar_keyboard("ida", 2026, 11, today=date(2026, 11, 25))
    assert "ida:nav:2026-10" not in _callbacks(kb)
    assert "ida:nav:2026-12" in _callbacks(kb)


def test_calendar_year_change():
    kb = calendar_keyboard("vuelta", 2026, 12, today=date(2026, 11, 25))
    assert "vuelta:nav:2027-01" in _callbacks(kb)
    assert "Diciembre 2026" in _texts(kb)


def test_times_keyboard_has_any_train_option():
    kb = times_keyboard("ida", ["07:00", "09:30"])
    assert _callbacks(kb) == ["ida:time:07:00", "ida:time:09:30", "ida:time:any"]


def test_describe_day():
    assert describe_day(date(2027, 3, 14)) == "domingo 14/03/2027"
