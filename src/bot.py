"""This module contains the main logic of the bot. The search process is a finite state machine."""

import asyncio
import json
import os
import signal
from datetime import datetime
from typing import Any, Dict

import requests
from pydantic import BaseModel
from telebot import async_telebot, asyncio_filters
from telebot.asyncio_storage import StateMemoryStorage
from telebot.states import State, StatesGroup
from telebot.states.asyncio.context import StateContext
from telebot.states.asyncio.middleware import StateMiddleware
from telebot.types import (BotCommand, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
                           KeyboardButton, Message, ReplyKeyboardMarkup,
                           ReplyKeyboardRemove)

import re
from datetime import date

from calendar_kb import NOOP, calendar_keyboard, describe_day, times_keyboard
from config import get_bot_token
from errors import InvalidDWRToken, InvalidTrainRideFilter
from messages import user_messages as msg, get_tickets_message
from models import TrainRideFilter, StationRecord
from scraper import Scraper
from validators import validate_station, validate_date, validate_float


class SearchStates(StatesGroup):
    """SearchStates is a class that defines the different states for the search process."""
    origin = State()
    destination = State()
    departure_date = State()
    departure_time = State()
    exact_time = State()
    exact_time_pick = State()
    needs_return = State()
    return_date = State()
    return_time = State()
    needs_filter = State()
    repeat_choice = State()
    max_price = State()
    max_duration_minutes = State()


class SearchContext(BaseModel):
    """SearchContext is a class that holds the context of the search process."""
    user_id: int
    origin: StationRecord | None = None
    destination: StationRecord | None = None
    departure_date: datetime | None = None
    return_date: datetime | None = None
    max_price: float | None = None
    max_duration_minutes: float | None = None


TOKEN = get_bot_token()
state_storage = StateMemoryStorage()  # TODO: Don't use this in production, (idk why, but use redis)
bot = async_telebot.AsyncTeleBot(TOKEN, state_storage=state_storage)

# Searches running right now, one per chat
ACTIVE_SEARCHES: Dict[int, asyncio.Task] = {}
# File where running searches are saved, so they survive a restart of the bot
SEARCHES_FILE = "searches.json"
# Last search started in each chat, for /repetir
LAST_SEARCHES_FILE = "last_searches.json"
# What each running search has done so far, for /estado
SEARCH_STATUS: Dict[int, Dict[str, Any]] = {}
# Set while the bot is shutting down: stopped searches are kept in SEARCHES_FILE
SHUTTING_DOWN = False


def _serialize(ctx: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for key, value in ctx.items():
        if isinstance(value, BaseModel):
            out[key] = {"__station__": value.model_dump()}
        elif isinstance(value, datetime):
            out[key] = {"__datetime__": value.isoformat()}
        else:
            out[key] = value
    return out


def _deserialize(data: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for key, value in data.items():
        if isinstance(value, dict) and "__station__" in value:
            out[key] = StationRecord(**value["__station__"])
        elif isinstance(value, dict) and "__datetime__" in value:
            out[key] = datetime.fromisoformat(value["__datetime__"])
        else:
            out[key] = value
    return out


def load_saved_searches(path: str = SEARCHES_FILE) -> Dict[int, Dict[str, Any]]:
    """Read the searches saved on disk. Returns {chat_id: search context}."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        return {int(chat_id): _deserialize(ctx) for chat_id, ctx in raw.items()}
    except (OSError, ValueError, TypeError) as e:
        print(f"No he podido leer {path}: {e}")
        return {}


def save_search(chat_id: int, ctx: Dict[str, Any] | None, path: str = SEARCHES_FILE) -> None:
    """Save (or remove, when ctx is None) the search of a chat in the given file."""
    searches = load_saved_searches(path)
    if ctx is None:
        searches.pop(chat_id, None)
    else:
        searches[chat_id] = ctx
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({str(k): _serialize(v) for k, v in searches.items()}, f, ensure_ascii=False,
                  indent=2)
    os.replace(tmp, path)


def describe_search(ctx: Dict[str, Any]) -> str:
    """Short human description of a search, e.g. 'MADRID (TODAS) → ZARAGOZA-DELICIAS, 14/03/2027 09:30'."""
    text = (f"{ctx['origin'].name} → {ctx['destination'].name}, "
            f"{ctx['departure_date'].strftime('%d/%m/%Y %H:%M')}")
    if ctx.get("exact_time"):
        text += " (solo ese tren)"
    if ctx.get("return_date"):
        text += f", vuelta {ctx['return_date'].strftime('%d/%m/%Y %H:%M')}"
    return text


def renfe_link(origin: StationRecord, destination: StationRecord, day: datetime) -> str:
    """renfe.com search already filled in with the stations and the day."""
    def station_id(station: StationRecord) -> str:
        parts = station.code.split(",")
        return parts[1] if len(parts) > 1 else station.code
    return ("https://www.renfe.com/es/es/buscador-billetes"
            f"?origin={station_id(origin)}&destination={station_id(destination)}"
            f"&departure-date={day:%Y-%m-%d}")


def buy_button(origin: StationRecord, destination: StationRecord, day: datetime
               ) -> InlineKeyboardMarkup:
    """Big button under the alert that opens the Renfe search for that trip."""
    kb = InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton("🎟️ Abrir en Renfe", url=renfe_link(origin, destination, day)))
    return kb


YES_ANSWERS = ["si", "sí", "s", "y", "yes"]


def is_yes(text: str | None) -> bool:
    """Whether the user answered yes."""
    return (text or "").strip().lower() in YES_ANSWERS


def keyboard(options: list[str]) -> ReplyKeyboardMarkup:
    """Telegram buttons under the text box, one per option, hidden after pressing one."""
    kb = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True, row_width=1)
    kb.add(*[KeyboardButton(option) for option in options])
    return kb


YES_NO = ["Sí", "No"]


def start_search_task(chat_id: int, ctx: Dict[str, Any]) -> None:
    """Save the search and run it in the background."""
    save_search(chat_id, ctx)
    save_search(chat_id, {k: v for k, v in ctx.items()
                          if k not in ("departure_done", "return_done")}, LAST_SEARCHES_FILE)
    ACTIVE_SEARCHES[chat_id] = asyncio.create_task(search_trains(chat_id, ctx))


@bot.message_handler(commands=["start"])
async def send_welcome(message: Message, state: StateContext):
    """Sends a welcome message to the user who initiated the conversation."""
    assert message.from_user is not None
    username = message.from_user.first_name
    await bot.send_message(message.chat.id, msg["welcome"].format(username))


@bot.message_handler(commands=["ayuda"])
async def send_help(message: Message):
    """Sends a help message to the user who requested it."""
    await bot.send_message(message.chat.id, msg["help"])


@bot.message_handler(commands=["cancelar"])
async def send_cancel(message: Message, state: StateContext):
    """Cancels the running search, or the parameter inputs if no search is running."""
    await state.delete()
    task = ACTIVE_SEARCHES.pop(message.chat.id, None)
    if task is not None:
        task.cancel()
        save_search(message.chat.id, None)
        await bot.send_message(message.chat.id, msg["cancel"])
    else:
        await bot.send_message(message.chat.id, msg["cancel_params"])


@bot.message_handler(commands=["prueba"])
async def send_test_alert(message: Message):
    """Sends an example seat alert after a few seconds (so the user can lock the phone), exactly
    like a real one, without touching running searches. '/prueba 30' waits 30 seconds."""
    parts = (message.text or "").split()
    delay = 15
    if len(parts) > 1 and parts[1].isdigit():
        delay = max(1, min(int(parts[1]), 600))
    await bot.send_message(message.chat.id, msg["test_scheduled"].format(delay))
    asyncio.create_task(_send_test_alert_later(message.chat.id, delay))


async def _send_test_alert_later(chat_id: int, delay: int) -> None:
    from models import TrainRideRecord
    from storage import StationsStorage
    await asyncio.sleep(delay)
    try:
        ctx = load_saved_searches().get(chat_id) or \
            load_saved_searches(LAST_SEARCHES_FILE).get(chat_id)
        origin = ctx["origin"] if ctx else StationsStorage.get_station("MADRID (TODAS)")
        destination = ctx["destination"] if ctx else StationsStorage.get_station("BARCELONA-SANTS")
        when = ctx["departure_date"] if ctx else datetime.now()
        if when.hour == 0 and when.minute == 0:
            when = when.replace(hour=9, minute=30)
        train = TrainRideRecord(origin=origin.name, destination=destination.name,
                                departure_time=when, arrival_time=when, duration=90,
                                price=0.0, available=True, not_on_sale_yet=False,
                                train_type="(EJEMPLO)", transfer_stations=[])
        text = msg["test_alert"] + get_tickets_message([train], origin, destination)
        await bot.send_message(chat_id, text,
                               reply_markup=buy_button(origin, destination, when))
    except Exception as e:
        await bot.send_message(chat_id, msg["undefined_exception"].format(repr(e)))


@bot.message_handler(commands=["estado"])
async def send_status(message: Message):
    """Tells the user whether their search is running and how it is going."""
    chat_id = message.chat.id
    task = ACTIVE_SEARCHES.get(chat_id)
    ctx = load_saved_searches().get(chat_id)
    if task is None or task.done() or ctx is None:
        await bot.send_message(chat_id, msg["status_none"])
        return
    st = SEARCH_STATUS.get(chat_id, {})
    last = st.get("last_check")
    last_text = f"{last:%H:%M:%S}" if last else "todavía ninguna"
    text = msg["status_running"].format(
        search=describe_search(ctx),
        since=f"{st['since']:%d/%m %H:%M}" if st.get("since") else "?",
        checks=st.get("checks", 0),
        last=last_text,
        result=st.get("last_result", "?"),
    )
    if st.get("failures", 0) >= 3:
        text += "\n" + msg["status_failing"].format(st["failures"])
    await bot.send_message(chat_id, text)


@bot.message_handler(commands=["debug"])
async def debug(message: Message, state: StateContext):
    """Debug the current state and data."""
    st = await state.get()
    running = message.chat.id in ACTIVE_SEARCHES
    await bot.send_message(message.chat.id, f"state={st} buscando={running}")


@bot.message_handler(commands=["buscar"])
async def start_search(message: Message, state: StateContext):
    """Starts the search process by asking the user for the origin station."""
    assert message.from_user is not None
    if message.chat.id in ACTIVE_SEARCHES:
        await bot.send_message(message.chat.id, msg["search_already_running"])
        return
    await state.set(SearchStates.origin)
    await bot.send_message(message.chat.id, msg["start"])


async def send_station_error(chat_id: int, result) -> None:
    """Tell the user the station wasn't found, with the closest ones as buttons."""
    markup = keyboard(result.suggestions) if result.suggestions else ReplyKeyboardRemove()
    await bot.send_message(chat_id, result.error_message, reply_markup=markup)


REPEAT_SAME, REPEAT_TIME, REPEAT_DAY = "🔁 Igual", "🕒 Cambiar la hora", "📅 Cambiar día y hora"


@bot.message_handler(commands=["repetir"])
async def repeat_search(message: Message, state: StateContext):
    """Repeats the last search of this chat, optionally changing the day or the time."""
    if message.chat.id in ACTIVE_SEARCHES:
        await bot.send_message(message.chat.id, msg["search_already_running"])
        return
    last = load_saved_searches(LAST_SEARCHES_FILE).get(message.chat.id)
    if last is None:
        await bot.send_message(message.chat.id, msg["nothing_to_repeat"])
        return
    last = {k: v for k, v in last.items() if k not in ("departure_done", "return_done")}
    await state.delete()
    await state.set(SearchStates.repeat_choice)
    await state.add_data(**last)
    options = [REPEAT_TIME, REPEAT_DAY]
    if last["departure_date"].date() >= date.today():
        options.insert(0, REPEAT_SAME)
    await bot.send_message(message.chat.id, msg["repeat_question"].format(describe_search(last)),
                           reply_markup=keyboard(options))


@bot.message_handler(state=SearchStates.repeat_choice)
async def repeat_choice(message: Message, state: StateContext):
    async with state.data() as data:  # type: ignore
        ctx = dict(data)
    choice = (message.text or "").strip()
    day: date = ctx["departure_date"].date()

    if choice == REPEAT_SAME and day >= date.today():
        await begin_search(message, state)
    elif choice == REPEAT_TIME and day >= date.today():
        await bot.send_message(message.chat.id, msg["ok"], reply_markup=ReplyKeyboardRemove())
        await ask_train_time(message.chat.id, state, "ida", day)
    elif choice in (REPEAT_DAY, REPEAT_TIME):
        if day < date.today():
            await bot.send_message(message.chat.id, msg["repeat_past_day"],
                                   reply_markup=ReplyKeyboardRemove())
        else:
            await bot.send_message(message.chat.id, msg["ok"], reply_markup=ReplyKeyboardRemove())
        await state.set(SearchStates.departure_date)
        await send_calendar(message.chat.id, "ida")
    else:
        await bot.send_message(message.chat.id, msg["repeat_pick"])


@bot.message_handler(state=SearchStates.origin)
async def origin_get(message: Message, state: StateContext):
    """Gets the origin station from the user and asks for the destination station."""
    origin = validate_station(message.text)

    if not origin:
        await send_station_error(message.chat.id, origin)
    else:
        await state.set(SearchStates.destination)
        await state.add_data(origin=origin.station)
        await bot.send_message(message.chat.id, msg["destination"],
                               reply_markup=ReplyKeyboardRemove())


@bot.message_handler(state=SearchStates.destination)
async def destination_get(message: Message, state: StateContext):
    """Gets the destination station from the user and asks for the departure date."""
    destination = validate_station(message.text)

    if not destination:
        await send_station_error(message.chat.id, destination)
    else:
        await state.set(SearchStates.departure_date)
        await state.add_data(destination=destination.station)
        await bot.send_message(message.chat.id, msg["station_ok"].format(destination.station.name),
                               reply_markup=ReplyKeyboardRemove())
        await send_calendar(message.chat.id, "ida")


@bot.message_handler(state=SearchStates.departure_date)
async def departure_date_get(message: Message, state: StateContext):
    """Gets the departure date from the user and asks if they need a return ticket."""
    departure_datetime = validate_date(message.text)

    if not departure_datetime:
        await bot.send_message(message.chat.id, departure_datetime.error_message)
    else:
        assert departure_datetime.date is not None
        await bot.send_message(
            message.chat.id,
            msg["confirm_date"].format(departure_datetime.date.strftime("%d/%m/%Y %H:%M")),
        )
        await state.set(SearchStates.exact_time)
        await state.add_data(departure_date=departure_datetime.date)
        await bot.send_message(message.chat.id, msg["exact_time"], reply_markup=keyboard(YES_NO))


# ---------- Calendar and train times ----------

async def send_calendar(chat_id: int, prefix: str) -> None:
    today = date.today()
    text = msg["destination_date"] if prefix == "ida" else msg["return_date"]
    await bot.send_message(chat_id, text, reply_markup=calendar_keyboard(prefix, today.year, today.month))


DAY_STATE = {"ida": SearchStates.departure_date, "vuelta": SearchStates.return_date}
TIME_STATE = {"ida": SearchStates.departure_time, "vuelta": SearchStates.return_time}


def _is_state(current: str | None, wanted: State) -> bool:
    return current is not None and current == wanted.name


@bot.callback_query_handler(func=lambda call: call.data == NOOP)
async def noop_callback(call: CallbackQuery):
    await bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: (call.data or "").split(":")[0] in ("ida", "vuelta"))
async def calendar_callback(call: CallbackQuery, state: StateContext):
    """Handles the calendar (change month, pick a day) and the train time buttons."""
    prefix, kind, value = call.data.split(":", 2)
    chat_id = call.message.chat.id
    current = await state.get()

    if kind == "nav" and _is_state(current, DAY_STATE[prefix]):
        year, month = map(int, value.split("-"))
        await bot.edit_message_reply_markup(chat_id, call.message.message_id,
                                            reply_markup=calendar_keyboard(prefix, year, month))
        await bot.answer_callback_query(call.id)
        return

    if kind == "day" and _is_state(current, DAY_STATE[prefix]):
        day = date.fromisoformat(value)
        await bot.answer_callback_query(call.id)
        label = "Ida" if prefix == "ida" else "Vuelta"
        await bot.edit_message_text(f"📅 {label}: {describe_day(day)}", chat_id,
                                    call.message.message_id)
        await ask_train_time(chat_id, state, prefix, day)
        return

    if kind == "time" and _is_state(current, TIME_STATE[prefix]):
        await bot.answer_callback_query(call.id)
        await bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=None)
        if value == "any":
            await set_train_time(chat_id, state, prefix, None, exact=False)
        else:
            hour, minute = map(int, value.split(":"))
            await set_train_time(chat_id, state, prefix, (hour, minute), exact=True)
        return

    await bot.answer_callback_query(call.id, msg["old_buttons"])


async def ask_train_time(chat_id: int, state: StateContext, prefix: str, day: date) -> None:
    """Show the departure times of that day's trains as buttons."""
    async with state.data() as data:  # type: ignore
        origin, destination = data["origin"], data["destination"]
    if prefix == "vuelta":
        origin, destination = destination, origin
    await state.add_data(**{f"{prefix}_day": day.isoformat()})
    await state.set(TIME_STATE[prefix])

    await bot.send_message(chat_id, msg["checking_time"])
    times: list[str] = []
    try:
        when = datetime(day.year, day.month, day.day)
        trains = await asyncio.to_thread(Scraper(origin, destination, when).get_trainrides)
        times = sorted({f"{t.departure_time:%H:%M}" for t in trains
                        if t.departure_time.date() == day and t.origin == origin.name})
    except Exception as e:  # Renfe failing: the user can still type a time
        print(f"No he podido consultar los horarios: {e!r}")

    if times:
        text = msg["pick_time"].format(origin.name, destination.name)
    else:
        text = msg["pick_time_unknown"]
    await bot.send_message(chat_id, text, reply_markup=times_keyboard(prefix, times))


async def set_train_time(chat_id: int, state: StateContext, prefix: str,
                         hour_minute: tuple[int, int] | None, exact: bool) -> None:
    """Store the chosen day and time and continue with the next question."""
    async with state.data() as data:  # type: ignore
        day = date.fromisoformat(data[f"{prefix}_day"])
    hour, minute = hour_minute or (0, 0)
    when = datetime(day.year, day.month, day.day, hour, minute)

    if prefix == "ida":
        await state.add_data(departure_date=when, exact_time=exact)
        if hour_minute is None:
            await bot.send_message(chat_id, msg["any_train"].format(describe_day(day)))
        elif exact:
            await bot.send_message(chat_id, msg["time_found"].format(f"{hour:02d}:{minute:02d}"))
        else:
            await bot.send_message(chat_id, msg["confirm_date"].format(when.strftime("%d/%m/%Y %H:%M")))
            await state.set(SearchStates.exact_time)
            await bot.send_message(chat_id, msg["exact_time"], reply_markup=keyboard(YES_NO))
            return
        await ask_needs_return(chat_id, state)
    else:
        await state.add_data(return_date=when)
        await bot.send_message(chat_id, msg["confirm_return"].format(when.strftime("%d/%m/%Y %H:%M")))
        await state.set(SearchStates.needs_filter)
        await bot.send_message(chat_id, msg["needs_filter"], reply_markup=keyboard(YES_NO))


TIME_RE = re.compile(r"^\s*(\d{1,2})(?:[:.h](\d{2}))?\s*h?\s*$")


async def typed_time(message: Message, state: StateContext, prefix: str) -> None:
    """The user typed a time instead of pressing a button: watch trains from that time on."""
    match = TIME_RE.match(message.text or "")
    if not match or int(match.group(1)) > 23:
        await bot.send_message(message.chat.id, msg["wrong_time"])
        return
    hour, minute = int(match.group(1)), int(match.group(2) or 0)
    if minute > 59:
        await bot.send_message(message.chat.id, msg["wrong_time"])
        return
    await set_train_time(message.chat.id, state, prefix, (hour, minute), exact=False)


@bot.message_handler(state=SearchStates.departure_time)
async def departure_time_typed(message: Message, state: StateContext):
    await typed_time(message, state, "ida")


@bot.message_handler(state=SearchStates.return_time)
async def return_time_typed(message: Message, state: StateContext):
    await typed_time(message, state, "vuelta")


@bot.message_handler(state=SearchStates.exact_time)
async def exact_time_get(message: Message, state: StateContext):
    """Asks whether only the train leaving at the exact given time should be watched."""
    exact = is_yes(message.text)
    await state.add_data(exact_time=exact)
    if exact:
        async with state.data() as data:  # type: ignore
            ctx = dict(data)
        if not await check_exact_time(message.chat.id, state, ctx):
            return
    await ask_needs_return(message.chat.id, state)


async def ask_needs_return(chat_id: int, state: StateContext) -> None:
    await state.set(SearchStates.needs_return)
    await bot.send_message(chat_id, msg["needs_return"], reply_markup=keyboard(YES_NO))


async def check_exact_time(chat_id: int, state: StateContext, ctx: Dict[str, Any]) -> bool:
    """Check with Renfe that a train leaves at the exact time asked. If none does, offer the
    closest ones as buttons and return False (the conversation waits for the user's pick)."""
    wanted: datetime = ctx["departure_date"]
    await bot.send_message(chat_id, msg["checking_time"], reply_markup=ReplyKeyboardRemove())
    try:
        scraper = Scraper(ctx["origin"], ctx["destination"], wanted)
        trains = await asyncio.to_thread(scraper.get_trainrides)
    except Exception as e:  # Renfe failing now: don't block the search because of the check
        print(f"No he podido comprobar los horarios: {e!r}")
        await bot.send_message(chat_id, msg["time_check_failed"].format(wanted.strftime("%H:%M")))
        return True

    day_trains = sorted((t for t in trains if t.departure_time.date() == wanted.date()),
                        key=lambda t: t.departure_time)
    if any(t.departure_time.hour == wanted.hour and t.departure_time.minute == wanted.minute
           for t in day_trains):
        await bot.send_message(chat_id, msg["time_found"].format(wanted.strftime("%H:%M")))
        return True

    if not day_trains:
        await state.set(SearchStates.departure_date)
        await bot.send_message(chat_id, msg["no_trains_that_day"])
        return False

    # Several trains can leave at the same time (e.g. direct and with a transfer): one entry each
    by_time: Dict[datetime, list] = {}
    for t in day_trains:
        by_time.setdefault(t.departure_time, []).append(t)
    closest = sorted(by_time, key=lambda when: abs(when - wanted))[:4]
    closest.sort()
    lines = []
    for when in closest:
        group = by_time[when]
        types = "/".join(sorted({t.train_type for t in group}))
        status = "hay plazas" if any(t.available for t in group) else "completo"
        lines.append(f"• {when:%H:%M} {types} ({status})")
    await state.add_data(time_options=sorted({f"{when:%H:%M}" for when in by_time}))
    await state.set(SearchStates.exact_time_pick)
    await bot.send_message(chat_id,
                           msg["time_not_found"].format(wanted.strftime("%H:%M"), "\n".join(lines)),
                           reply_markup=keyboard([f"{when:%H:%M}" for when in closest]))
    return False


@bot.message_handler(state=SearchStates.exact_time_pick)
async def exact_time_pick(message: Message, state: StateContext):
    """Gets the train time the user picked among the real ones."""
    text = (message.text or "").strip().replace(".", ":")
    async with state.data() as data:  # type: ignore
        options = list(data.get("time_options", []))
        wanted: datetime = data["departure_date"]
    if len(text) == 4 and text[1] == ":":
        text = "0" + text
    if text not in options:
        await bot.send_message(message.chat.id, msg["time_pick_invalid"].format(", ".join(options)))
        return
    hour, minute = map(int, text.split(":"))
    await state.add_data(departure_date=wanted.replace(hour=hour, minute=minute))
    await bot.send_message(message.chat.id, msg["time_found"].format(text),
                           reply_markup=ReplyKeyboardRemove())
    await ask_needs_return(message.chat.id, state)


@bot.message_handler(state=SearchStates.needs_return)
async def return_get(message: Message, state: StateContext):
    """Gets the user's choice about needing a return ticket and asks for the date if he needs."""
    if is_yes(message.text):
        await state.set(SearchStates.return_date)
        await bot.send_message(message.chat.id, msg["ok"], reply_markup=ReplyKeyboardRemove())
        await send_calendar(message.chat.id, "vuelta")
    else:
        await state.add_data(return_date=None)
        await state.set(SearchStates.needs_filter)
        await bot.send_message(message.chat.id, msg["needs_filter"], reply_markup=keyboard(YES_NO))


@bot.message_handler(state=SearchStates.return_date)
async def return_date_get(message: Message, state: StateContext):
    """Gets the return date from the user and asks if they want to filter the results."""
    return_datetime = validate_date(message.text)

    if not return_datetime:
        await bot.send_message(message.chat.id, return_datetime.error_message)
    else:
        assert return_datetime.date is not None
        await bot.send_message(
            message.chat.id,
            msg["confirm_date"].format(return_datetime.date.strftime("%d/%m/%Y %H:%M")),
        )
        await state.set(SearchStates.needs_filter)
        await state.add_data(return_date=return_datetime.date)
        await bot.send_message(message.chat.id, msg["needs_filter"], reply_markup=keyboard(YES_NO))


async def begin_search(message: Message, state: StateContext):
    """Takes the parameters collected in the conversation and starts the background search."""
    async with state.data() as data:  # type: ignore
        ctx = dict(data)
    await state.delete()
    for key in ("time_options", "ida_day", "vuelta_day"):
        ctx.pop(key, None)
    await bot.send_message(message.chat.id, msg["searching"], reply_markup=ReplyKeyboardRemove())
    start_search_task(message.chat.id, ctx)


@bot.message_handler(state=SearchStates.needs_filter)
async def ask_for_filter(message: Message, state: StateContext):
    """Asks the user if they want to filter the results and starts the search process if not."""
    if is_yes(message.text):
        await state.set(SearchStates.max_price)
        await bot.send_message(message.chat.id, msg["max_price"], reply_markup=ReplyKeyboardRemove())
    else:
        await state.add_data(max_price=None, max_duration_minutes=None)
        await begin_search(message, state)


@bot.message_handler(state=SearchStates.max_price)
async def ask_for_max_price(message: Message, state: StateContext):
    """Asks the user for the maximum price and starts the search process."""
    parsed = validate_float(message.text)

    if not parsed:
        await bot.send_message(message.chat.id, parsed.error_message)
    else:
        await state.set(SearchStates.max_duration_minutes)
        await state.add_data(max_price=None if parsed.number == 0 else parsed.number)
        await bot.send_message(message.chat.id, msg["max_duration"])


@bot.message_handler(state=SearchStates.max_duration_minutes)
async def get_max_duration(message: Message, state: StateContext):
    """Gets the maximum duration of the trip and starts the search process."""
    parsed = validate_float(message.text)

    if not parsed:
        await bot.send_message(message.chat.id, parsed.error_message)
    else:
        await state.add_data(max_duration_minutes=None if parsed.number == 0 else parsed.number)
        await begin_search(message, state)


async def search_trains(chat_id: int, ctx: Dict[str, Any]):
    """Checks Renfe every minute until the wanted trains have seats, then tells the user."""
    print(f"[{chat_id}] Empiezo a buscar: {describe_search(ctx)}")
    status = SEARCH_STATUS[chat_id] = {"since": datetime.now(), "checks": 0, "last_check": None,
                                        "last_result": "todavía no he consultado Renfe",
                                        "failures": 0}
    departure_done = ctx.get("departure_done", False)
    return_done = ctx.get("return_done", False) or ctx.get("return_date") is None

    scraper = Scraper(ctx["origin"],
                      ctx["destination"],
                      ctx["departure_date"],
                      ctx.get("return_date"))

    departure_filter = TrainRideFilter(origin=ctx["origin"].name,
                                       destination=ctx["destination"].name,
                                       departure_date=ctx["departure_date"],
                                       max_duration_minutes=ctx.get("max_duration_minutes"),
                                       max_price=ctx.get("max_price"),
                                       exact_time=ctx.get("exact_time", False))

    if not return_done:
        return_filter = TrainRideFilter(origin=ctx["destination"].name,
                                        destination=ctx["origin"].name,
                                        departure_date=ctx["return_date"],
                                        max_duration_minutes=ctx.get("max_duration_minutes"),
                                        max_price=ctx.get("max_price"))

    finished = False
    failures = 0
    try:
        while not departure_done or not return_done:
            # The scraper is blocking (requests), run it outside the event loop
            try:
                trains = await asyncio.to_thread(scraper.get_trainrides)
                failures = 0
                status.update(checks=status["checks"] + 1, last_check=datetime.now(), failures=0)
            except (requests.RequestException, AssertionError) as e:
                # No internet or Renfe failing for a moment: try again later instead of giving up
                failures += 1
                status.update(last_check=datetime.now(), failures=failures,
                              last_result="no he podido consultar Renfe (sin internet o su web falla)")
                print(f"Error consultando Renfe ({e!r}), intento fallido {failures}, reintento en 60 s")
                if failures == 10:
                    await bot.send_message(chat_id, msg["search_failing"])
                await asyncio.sleep(60)
                continue
            if not departure_done:
                departure_trains = departure_filter.filter_rides(trains)
                departure_done = len(departure_trains) > 0
                status["last_result"] = ("¡hay plaza!" if departure_done
                                         else "sigue completo, sin plazas")
                if departure_done:
                    ctx["departure_done"] = True
                    save_search(chat_id, ctx)
                    await bot.send_message(chat_id,
                                           get_tickets_message(departure_trains,
                                                               ctx["origin"],
                                                               ctx["destination"]),
                                           reply_markup=buy_button(ctx["origin"],
                                                                   ctx["destination"],
                                                                   ctx["departure_date"]))
            if not return_done:
                return_trains = return_filter.filter_rides(trains)
                return_done = len(return_trains) > 0
                if return_done:
                    ctx["return_done"] = True
                    save_search(chat_id, ctx)
                    await bot.send_message(chat_id,
                                           get_tickets_message(return_trains,
                                                               ctx["destination"],
                                                               ctx["origin"]),
                                           reply_markup=buy_button(ctx["destination"],
                                                                   ctx["origin"],
                                                                   ctx["return_date"]))
            if not return_done or not departure_done:
                await asyncio.sleep(60)
        finished = True
        print(f"[{chat_id}] Encontrados los trenes buscados, fin de la búsqueda")

    except asyncio.CancelledError:
        # /cancelar or the bot is stopping: whoever cancelled decides what to do with the save
        raise

    except InvalidTrainRideFilter:
        finished = True
        print(f"[{chat_id}] Ningún tren encaja con el filtro, fin de la búsqueda")
        await bot.send_message(chat_id, msg["invalid_filter"])

    except InvalidDWRToken:
        finished = True
        await bot.send_message(chat_id, msg["invalid_dwr_token"])

    except Exception as e:
        finished = True
        print(f"[{chat_id}] Error inesperado en la búsqueda: {e!r}")
        await bot.send_message(chat_id, msg["undefined_exception"].format(str(e)))

    finally:
        if finished and not SHUTTING_DOWN:
            ACTIVE_SEARCHES.pop(chat_id, None)
            SEARCH_STATUS.pop(chat_id, None)
            save_search(chat_id, None)


async def resume_saved_searches() -> None:
    """Restart the searches that were running when the bot stopped, and tell their users."""
    for chat_id, ctx in load_saved_searches().items():
        try:
            await bot.send_message(chat_id, msg["search_resumed"].format(describe_search(ctx)))
        except Exception as e:  # e.g. the user blocked the bot
            print(f"No he podido avisar al chat {chat_id}: {e}")
        ACTIVE_SEARCHES[chat_id] = asyncio.create_task(search_trains(chat_id, ctx))


async def notify_stopping() -> None:
    """Tell every user with a running search that the bot is stopping."""
    saved = load_saved_searches()
    for chat_id in list(ACTIVE_SEARCHES):
        ctx = saved.get(chat_id)
        if ctx is None:
            continue
        try:
            await bot.send_message(chat_id, msg["search_paused"].format(describe_search(ctx)))
        except Exception as e:
            print(f"No he podido avisar al chat {chat_id}: {e}")


async def main() -> None:
    """Run the bot until SIGINT (Ctrl+C) or SIGTERM (systemctl stop), then stop it cleanly."""
    global SHUTTING_DOWN

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # Windows: fall back to signal.signal
            signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stop.set))

    bot.add_custom_filter(asyncio_filters.StateFilter(bot))
    bot.setup_middleware(StateMiddleware(bot))

    try:
        await bot.set_my_commands([
            BotCommand("buscar", "Buscar billetes de tren"),
            BotCommand("repetir", "Repetir la última búsqueda"),
            BotCommand("cancelar", "Cancelar la búsqueda en curso"),
            BotCommand("estado", "Ver si tu búsqueda sigue activa"),
            BotCommand("prueba", "Recibir un aviso de ejemplo"),
            BotCommand("ayuda", "Ver los comandos"),
        ])
    except Exception as e:
        print(f"No he podido registrar el menú de comandos: {e!r}")
    await resume_saved_searches()
    polling = asyncio.create_task(bot.infinity_polling())
    print("Ya estoy corriendo! Corre a Telegram e interactúa conmigo con los comandos /start o /help")

    await stop.wait()
    print("Parando el bot...")
    SHUTTING_DOWN = True
    await notify_stopping()

    for task in ACTIVE_SEARCHES.values():
        task.cancel()
    await asyncio.gather(*ACTIVE_SEARCHES.values(), return_exceptions=True)
    await bot.stop_polling() if hasattr(bot, "stop_polling") else None
    polling.cancel()
    await asyncio.gather(polling, return_exceptions=True)
    await bot.close_session()
    print("Bot parado. Las búsquedas en curso se retomarán al volver a arrancarlo.")


if __name__ == "__main__":
    asyncio.run(main())
