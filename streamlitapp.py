from functools import partial
import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import date

from telegram.ext import Updater
import logging
from telegram import Update
from telegram.ext import CallbackContext
from telegram.ext import CommandHandler


from oauth2client.service_account import ServiceAccountCredentials
import gspread


st.title("Telegram bot dashboard")

HELP = "commands /start, /register, /yesterday <hh> <mm>"

# @st.experimental_singleton
def _get_db():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    secrets = dict(st.secrets)
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(secrets, scopes)
    file = gspread.authorize(credentials)  # authenticate the JSON key with gspread
    sheet = file.open("TheTimeSink")  # open sheet
    return sheet.worksheet("database")


def _get_dataframe(return_db=False):
    db = _get_db()
    df = pd.DataFrame(db.get_all_records()).set_index("Dia")
    df.index = pd.to_datetime(df.index, dayfirst=True)
    df = df.applymap(lambda x: pd.to_timedelta(x, errors="coerce"))
    if return_db:
        return df, db
    return df


def read_column(column):
    db = _get_db()
    print(db.col_values(column))


def _username(update):
    user = update.message.from_user
    username = (
        user.username or user.first_name or user.name or user.full_name or user.id
    )
    username = username.lower()
    return username


def register_user(update: Update, context: CallbackContext):
    username = _username(update)
    db = _get_db()
    users = db.row_values(1)[1:]

    if username in users:
        resp = "Ja estas registrat cabron."
    else:
        resp = f"Hola {username}, benvingut."
        user_col = len(users) + 1
        db.update_cell(1, user_col, username)
    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=resp,
        reply_to_message_id=update.message.message_id,
    )


def _check_user(update, context, df=None):
    username = _username(update)
    if df is None:
        df = _get_dataframe()
    users = df.columns
    if username not in users:
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Usuari no registrat",
            reply_to_message_id=update.message.message_id,
        )
        return
    return username


def summary(update: Update, context: CallbackContext):
    df = _get_dataframe()
    username = _check_user(update, context, df=df)
    val = df[username]
    total, high, low, avg = (
        val.sum().components,
        val.max().components,
        val.min().components,
        val.mean().components,
    )
    resp = f"""
En total has passat {total.days} dies, {total.hours} hores i {total.minutes} minuts mirant el mobil.
El teu record en un dia es de {high.hours} hores i {high.minutes} minuts.
I el minim que has aconseguit es de {low.hours} hores i {low.minutes} minuts.
La teva mitjana diaria es de {avg.hours} hores i {avg.minutes} minuts.
            """
    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=resp,
        reply_to_message_id=update.message.message_id,
    )


def start(update: Update, context: CallbackContext):
    user = update.message.from_user
    username = (
        user.username or user.first_name or user.name or user.full_name or user.id
    )
    username = username.lower()
    resp = f"Fa pal escriure descripcio, hola {username}, i tal. Commandes son: " + HELP
    message_id = update.message.message_id
    context.bot.send_message(
        chat_id=update.effective_chat.id, text=resp, reply_to_message_id=message_id
    )


def reminder(update: Update, context: CallbackContext):
    df = _get_dataframe()
    _yesterday = pd.Timestamp(date.today() - pd.Timedelta(days=1))
    users = df.columns
    was_empty = False
    if _yesterday not in df.index:
        df.loc[_yesterday] = [pd.NaT] * len(users)
        was_empty = True
    values = df.loc[_yesterday]
    done = []
    pending = []
    for usr, val in zip(users, values):
        if pd.isnull(val):
            pending.append("@" + usr)
        else:
            done.append("@" + usr)

    if not done:
        message = "Ningu ha marcat encara el seu us d'ahir"
    elif not pending:
        message = "Tots els usuaris han marcat l'us d'ahir"
    elif len(pending) == 1:
        message = (
            f"Tots els usuaris han marcat l'us d'ahir, excepte {pending[0]}, espavila."
        )
    else:
        message = f"{', '.join(done)} ja han marcat, falten {', '.join(pending)}."
    context.bot.send_message(chat_id=update.effective_chat.id, text=message)


def yesterday(update: Update, context: CallbackContext):
    value = context.args
    if len(value) != 2 or not all([v.isdigit() and len(v) == 2 for v in value]):
        resp = "Commanda en mal format. Escriu: '/yesterday hh mm' (hours minutes)"
        context.bot.send_message(chat_id=update.effective_chat.id, text=resp)
        return
    df, db = _get_dataframe(return_db=True)
    username = _check_user(update, context, df=df)
    # delta = pd.Timedelta(hours=int(value[0]), minutes=int(value[1])).seconds
    delta_str = f"{int(value[0]):02d}:{int(value[1]):02d}:00"
    _yesterday = pd.Timestamp(date.today() - pd.Timedelta(days=1))
    if _yesterday not in df.index:
        resp = f"This should not happen. Yesterday row not in database. Check google sheets"
    else:
        row = df.index.get_loc(_yesterday) + 2
        col = df.columns.get_loc(username) + 2
        db.update_cell(row, col, delta_str)
        resp = f"M'apunto que ahir vas passar {value[0]} hores i {value[1]} minuts."
    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=resp,
        reply_to_message_id=update.message.message_id,
    )
    reminder(update, context)


def _create_updater():
    token = st.secrets["BOT_TOKEN"]
    updater = Updater(token=token, use_context=True)
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    dispatcher = updater.dispatcher
    start_handler = CommandHandler("start", start)
    dispatcher.add_handler(start_handler)
    updater.start_polling()
    register_handler = CommandHandler("register", register_user)
    dispatcher.add_handler(register_handler)
    yesterday_handler = CommandHandler("yesterday", yesterday)
    dispatcher.add_handler(yesterday_handler)
    summary_handler = CommandHandler("summary", summary)
    dispatcher.add_handler(summary_handler)
    reminder_handler = CommandHandler("reminder", reminder)
    dispatcher.add_handler(reminder_handler)
    return updater


@st.experimental_singleton
def get_updater():
    return {
        "active": False,
        "updater": None,
    }


def start_telegram_bot():
    updater = get_updater()
    if not updater["active"]:
        updater["updater"] = _create_updater()
        updater["active"] = True
        return
    st.text("Already running")


def stop_bot():
    updater = get_updater()
    if updater["active"]:
        updater["updater"]: _create_updater()
        updater["updater"].stop()
        updater["updater"] = None
        updater["active"] = False
        return
    st.text("It is not running")


def restart_bot():
    updater = get_updater()
    if updater["active"]:
        stop_bot()
    start_telegram_bot()


def show_st_dataframe():
    df = _get_dataframe()
    st.code(df)
    st.write(df.dtypes)


st.button("Start bot", on_click=start_telegram_bot)
st.button("Stop bot", on_click=stop_bot)
st.button("Restart bot", on_click=restart_bot)
st.button("Print df", on_click=show_st_dataframe)

up = get_updater()
st.markdown("## The bot is running" if up["active"] else "## Nothing running.")
