"""Inline keyboards for picking a day on a calendar and a train departure time in Telegram."""

import calendar
from datetime import date
from typing import List

from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

MONTHS = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto",
          "Septiembre", "Octubre", "Noviembre", "Diciembre"]
WEEKDAYS = ["L", "M", "X", "J", "V", "S", "D"]
WEEKDAY_NAMES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
NOOP = "noop"


def _noop(text: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text, callback_data=NOOP)


def calendar_keyboard(prefix: str, year: int, month: int, today: date | None = None
                      ) -> InlineKeyboardMarkup:
    """Month calendar. Days before today can't be picked.

    Callback data: '<prefix>:day:YYYY-MM-DD' for a day and '<prefix>:nav:YYYY-MM' to change month.
    """
    today = today or date.today()
    kb = InlineKeyboardMarkup(row_width=7)
    kb.row(_noop(f"{MONTHS[month - 1]} {year}"))
    kb.row(*[_noop(d) for d in WEEKDAYS])

    for week in calendar.Calendar(firstweekday=0).monthdayscalendar(year, month):
        row = []
        for day in week:
            if day == 0:
                row.append(_noop(" "))
            elif date(year, month, day) < today:
                row.append(_noop("·"))
            else:
                row.append(InlineKeyboardButton(
                    str(day), callback_data=f"{prefix}:day:{year:04d}-{month:02d}-{day:02d}"))
        kb.row(*row)

    prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
    next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
    can_go_back = (prev_year, prev_month) >= (today.year, today.month)
    kb.row(
        InlineKeyboardButton("◀", callback_data=f"{prefix}:nav:{prev_year:04d}-{prev_month:02d}")
        if can_go_back else _noop(" "),
        InlineKeyboardButton("▶", callback_data=f"{prefix}:nav:{next_year:04d}-{next_month:02d}"),
    )
    return kb


def times_keyboard(prefix: str, times: List[str]) -> InlineKeyboardMarkup:
    """One button per train departure time (4 per row) and one to accept any train that day.

    Callback data: '<prefix>:time:HH:MM' or '<prefix>:time:any'.
    """
    kb = InlineKeyboardMarkup(row_width=4)
    buttons = [InlineKeyboardButton(t, callback_data=f"{prefix}:time:{t}") for t in times]
    for i in range(0, len(buttons), 4):
        kb.row(*buttons[i:i + 4])
    kb.row(InlineKeyboardButton("Cualquier tren ese día", callback_data=f"{prefix}:time:any"))
    return kb


def describe_day(day: date) -> str:
    """'domingo 14/03/2027'"""
    return f"{WEEKDAY_NAMES[day.weekday()]} {day:%d/%m/%Y}"
