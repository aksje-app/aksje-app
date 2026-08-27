
from datetime import datetime, date, time, timedelta
import pytz

try:
    import pandas_market_calendars as mcal
except Exception:
    mcal = None


MARKETS = {
    "USA": {
        "name": "USA",
        "calendar": "XNYS",
        "tz": "America/New_York",
        "open": time(9, 30),
        "close": time(16, 0),
    },
    "NORGE": {
        "name": "Norge",
        "calendar": "XOSL",
        "tz": "Europe/Oslo",
        "open": time(9, 0),
        "close": time(16, 25),
    },
    "SVERIGE": {
        "name": "Sverige",
        "calendar": "XSTO",
        "tz": "Europe/Stockholm",
        "open": time(9, 0),
        "close": time(17, 30),
    },
    "FINLAND": {
        "name": "Finland",
        "calendar": "XHEL",
        "tz": "Europe/Helsinki",
        "open": time(10, 0),
        "close": time(18, 30),
    },
    "DANMARK": {
        "name": "Danmark",
        "calendar": "XCSE",
        "tz": "Europe/Copenhagen",
        "open": time(9, 0),
        "close": time(17, 0),
    },
    "BRASIL": {
        "name": "Brasil",
        "calendar": "BVMF",
        "tz": "America/Sao_Paulo",
        "open": time(10, 0),
        "close": time(17, 55),
    },
}


def now_oslo():
    return datetime.now(pytz.timezone("Europe/Oslo"))


def _market_now(market):
    cfg = MARKETS[market]
    return datetime.now(pytz.timezone(cfg["tz"]))


def _observed_fixed(d, weekday):
    """
    Enkel observed-regel for USA:
    - lørdag => fredag
    - søndag => mandag
    """
    if weekday == 5:
        return d - timedelta(days=1)
    if weekday == 6:
        return d + timedelta(days=1)
    return d


def _nth_weekday(year, month, weekday, n):
    d = date(year, month, 1)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d + timedelta(days=7 * (n - 1))


def _last_weekday(year, month, weekday):
    if month == 12:
        d = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        d = date(year, month + 1, 1) - timedelta(days=1)
    while d.weekday() != weekday:
        d -= timedelta(days=1)
    return d


def _easter_sunday(year):
    """
    Western Easter algorithm.
    """
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _midsummer_eve_sweden(year):
    # Friday between June 19 and June 25.
    d = date(year, 6, 19)
    while d.weekday() != 4:
        d += timedelta(days=1)
    return d


def _manual_holidays(market, year):
    """
    Fallback calendar if pandas_market_calendars is unavailable.
    Covers common full-day market holidays. It is intentionally conservative.
    """
    easter = _easter_sunday(year)
    holidays = set()

    if market == "USA":
        jan1 = date(year, 1, 1)
        juneteenth = date(year, 6, 19)
        july4 = date(year, 7, 4)
        christmas = date(year, 12, 25)

        holidays.update({
            _observed_fixed(jan1, jan1.weekday()),
            _nth_weekday(year, 1, 0, 3),      # MLK Day
            _nth_weekday(year, 2, 0, 3),      # Presidents Day
            easter - timedelta(days=2),       # Good Friday
            _last_weekday(year, 5, 0),        # Memorial Day
            _observed_fixed(juneteenth, juneteenth.weekday()),
            _observed_fixed(july4, july4.weekday()),
            _nth_weekday(year, 9, 0, 1),      # Labor Day
            _nth_weekday(year, 11, 3, 4),     # Thanksgiving
            _observed_fixed(christmas, christmas.weekday()),
        })

    elif market == "NORGE":
        holidays.update({
            date(year, 1, 1),
            easter - timedelta(days=3),       # Maundy Thursday
            easter - timedelta(days=2),       # Good Friday
            easter + timedelta(days=1),       # Easter Monday
            date(year, 5, 1),
            date(year, 5, 17),
            date(year, 12, 24),
            date(year, 12, 25),
            date(year, 12, 26),
            date(year, 12, 31),
        })

    elif market == "SVERIGE":
        holidays.update({
            date(year, 1, 1),
            date(year, 1, 6),
            easter - timedelta(days=2),       # Good Friday
            easter + timedelta(days=1),       # Easter Monday
            date(year, 5, 1),
            easter + timedelta(days=39),      # Ascension Day
            date(year, 6, 6),
            _midsummer_eve_sweden(year),
            date(year, 12, 24),
            date(year, 12, 25),
            date(year, 12, 26),
            date(year, 12, 31),
        })

    elif market == "FINLAND":
        holidays.update({
            date(year, 1, 1),
            date(year, 1, 6),
            easter - timedelta(days=2),
            easter + timedelta(days=1),
            date(year, 5, 1),
            easter + timedelta(days=39),
            _midsummer_eve_sweden(year),
            date(year, 12, 24),
            date(year, 12, 25),
            date(year, 12, 26),
        })

    elif market == "DANMARK":
        holidays.update({
            date(year, 1, 1),
            easter - timedelta(days=3),
            easter - timedelta(days=2),
            easter + timedelta(days=1),
            easter + timedelta(days=26),
            easter + timedelta(days=39),
            easter + timedelta(days=50),
            date(year, 6, 5),
            date(year, 12, 24),
            date(year, 12, 25),
            date(year, 12, 26),
            date(year, 12, 31),
        })

    elif market == "BRASIL":
        holidays.update({
            date(year, 1, 1),
            easter - timedelta(days=2),
            date(year, 4, 21),
            date(year, 5, 1),
            date(year, 9, 7),
            date(year, 10, 12),
            date(year, 11, 2),
            date(year, 11, 15),
            date(year, 12, 24),
            date(year, 12, 25),
            date(year, 12, 31),
        })

    return holidays


def _calendar_open_from_package(market, now_local):
    """
    Uses pandas_market_calendars if available.
    Returns None if package/calendar unavailable, otherwise status dict.
    """
    if mcal is None:
        return None

    cfg = MARKETS[market]
    try:
        cal = mcal.get_calendar(cfg["calendar"])
        d = now_local.date()
        schedule = cal.schedule(start_date=d, end_date=d)

        if schedule.empty:
            reason = "helg" if now_local.weekday() >= 5 else "helligdag"
            return {"is_open": False, "reason": reason}

        row = schedule.iloc[0]
        market_open = row["market_open"].to_pydatetime().astimezone(now_local.tzinfo)
        market_close = row["market_close"].to_pydatetime().astimezone(now_local.tzinfo)

        is_open = market_open <= now_local <= market_close

        if is_open:
            return {
                "is_open": True,
                "reason": "åpent",
                "opens_at": market_open.strftime("%H:%M"),
                "closes_at": market_close.strftime("%H:%M"),
            }

        if now_local < market_open:
            return {
                "is_open": False,
                "reason": f"ikke åpnet ennå ({market_open.strftime('%H:%M')})",
                "opens_at": market_open.strftime("%H:%M"),
                "closes_at": market_close.strftime("%H:%M"),
            }

        return {
            "is_open": False,
            "reason": f"stengt for dagen ({market_close.strftime('%H:%M')})",
            "opens_at": market_open.strftime("%H:%M"),
            "closes_at": market_close.strftime("%H:%M"),
        }

    except Exception as e:
        return None


def market_status(market, now=None):
    market = str(market).upper()
    if market not in MARKETS:
        return {
            "market": market,
            "is_open": False,
            "reason": "ukjent marked",
            "label": f"{market} stengt: ukjent marked",
        }

    cfg = MARKETS[market]
    tz = pytz.timezone(cfg["tz"])
    now_local = now.astimezone(tz) if now else datetime.now(tz)

    # Package calendar first
    pkg_status = _calendar_open_from_package(market, now_local)
    if pkg_status is not None:
        status = {
            "market": market,
            "name": cfg["name"],
            "local_time": now_local.strftime("%Y-%m-%d %H:%M"),
            **pkg_status,
        }
        status["label"] = _format_status_line(status)
        return status

    # Manual fallback
    local_date = now_local.date()

    if now_local.weekday() >= 5:
        status = {
            "market": market,
            "name": cfg["name"],
            "is_open": False,
            "reason": "helg",
            "local_time": now_local.strftime("%Y-%m-%d %H:%M"),
            "opens_at": cfg["open"].strftime("%H:%M"),
            "closes_at": cfg["close"].strftime("%H:%M"),
        }
        status["label"] = _format_status_line(status)
        return status

    if local_date in _manual_holidays(market, local_date.year):
        status = {
            "market": market,
            "name": cfg["name"],
            "is_open": False,
            "reason": "helligdag",
            "local_time": now_local.strftime("%Y-%m-%d %H:%M"),
            "opens_at": cfg["open"].strftime("%H:%M"),
            "closes_at": cfg["close"].strftime("%H:%M"),
        }
        status["label"] = _format_status_line(status)
        return status

    local_t = now_local.time()
    is_open = cfg["open"] <= local_t <= cfg["close"]

    if is_open:
        reason = "åpent"
    elif local_t < cfg["open"]:
        reason = f"ikke åpnet ennå ({cfg['open'].strftime('%H:%M')})"
    else:
        reason = f"stengt for dagen ({cfg['close'].strftime('%H:%M')})"

    status = {
        "market": market,
        "name": cfg["name"],
        "is_open": is_open,
        "reason": reason,
        "local_time": now_local.strftime("%Y-%m-%d %H:%M"),
        "opens_at": cfg["open"].strftime("%H:%M"),
        "closes_at": cfg["close"].strftime("%H:%M"),
    }
    status["label"] = _format_status_line(status)
    return status


def _format_status_line(status):
    name = status.get("name") or status.get("market")
    if status.get("is_open"):
        close = status.get("closes_at")
        return f"{name} åpent ✅" + (f" til {close}" if close else "")
    return f"{name} stengt: {status.get('reason', 'ukjent')}"


ALL_MARKETS = ("USA", "NORGE", "SVERIGE", "FINLAND", "DANMARK", "BRASIL")


def market_statuses(markets=None):
    selected = tuple(markets or ALL_MARKETS)
    return {m: market_status(m) for m in selected if m in ALL_MARKETS}


def market_status_lines(markets=None):
    selected = tuple(markets or ALL_MARKETS)
    return [market_status(m)["label"] for m in selected if m in ALL_MARKETS]


def open_markets(markets=None):
    return [m for m, s in market_statuses(markets).items() if s.get("is_open")]


def ticker_market(ticker):
    ticker = str(ticker).upper()
    if ticker.endswith(".OL"):
        return "NORGE"
    if ticker.endswith(".ST"):
        return "SVERIGE"
    if ticker.endswith(".HE"):
        return "FINLAND"
    if ticker.endswith(".CO"):
        return "DANMARK"
    if ticker.endswith(".SA"):
        return "BRASIL"
    return "USA"


def is_market_open_for_ticker(ticker):
    return market_status(ticker_market(ticker)).get("is_open", False)


def should_process_ticker(ticker):
    return is_market_open_for_ticker(ticker)
