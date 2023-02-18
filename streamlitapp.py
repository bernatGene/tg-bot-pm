from pathlib import Path
from functools import partial
from datetime import datetime
import pytz
import logging

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

import asyncio


from telegram.ext import Updater
from telegram import Update
from telegram.ext import CallbackContext, Filters
from telegram.ext import CommandHandler, MessageHandler


from oauth2client.service_account import ServiceAccountCredentials
import gspread

st.camera_input("Test")

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

def set_ticker(Q, update: Update, context: CallbackContext):
    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Setting ticker",
        reply_to_message_id=update.message.message_id,
    )
    
    Q.put_nowait({'update': update, "context": context})


def register_user(update: Update, context: CallbackContext):
    username = _username(update)
    db = _get_db()
    users = db.row_values(1)[1:]

    if username in users:
        resp = "Ja estas registrat cabron."
    else:
        resp = f"Hola {username}, benvingut."
        user_col = len(users) + 2
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
    _y = datetime.now(tz=pytz.timezone("Europe/Paris")) - pd.Timedelta(days=1)
    day, month, year = _y.day, _y.month, _y.year
    _yesterday = pd.Timestamp(day=day, month=month, year=year)
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
    if len(value) != 2 or not all([v.isdigit() and len(v) <= 2 for v in value]):
        resp = "Commanda en mal format. Escriu: '/yesterday hh mm' (hours minutes)"
        context.bot.send_message(chat_id=update.effective_chat.id, text=resp)
        return
    df, db = _get_dataframe(return_db=True)
    username = _check_user(update, context, df=df)
    h, m = int(value[0]), int(value[1])
    delta_str = f"{h:02d}:{m:02d}:00"
    _y = datetime.now(tz=pytz.timezone("Europe/Paris")) - pd.Timedelta(days=1)
    day, month, year = _y.day, _y.month, _y.year
    _yesterday = pd.Timestamp(day=day, month=month, year=year)
    if _yesterday not in df.index:
        resp = f"This should not happen. Yesterday row not in database. Check google sheets"
    else:
        row = df.index.get_loc(_yesterday) + 2
        col = df.columns.get_loc(username) + 2
        db.update_cell(row, col, delta_str)
        resp = f"M'apunto que ahir vas passar {h} hor{'a' if h == 1 else 'es'} i {m} minut{'s' if m != 1 else ''}."
    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=resp,
        reply_to_message_id=update.message.message_id,
    )
    reminder(update, context)


def rolling_avg(update: Update, context: CallbackContext):
    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Dibuixant el gràfic...",
        reply_to_message_id=update.message.message_id,
    )
    generate_rolling_avg_plot()
    img = Path("plot.png").read_bytes()
    context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=img,
        caption="Mitjana setmanal rodant. (Per a cada dia, la mitjana dels últims 7)",
    )

def trendline(update: Update, context: CallbackContext):
    args = context.args
    period = 300 
    text = "Calculant..."
    if len(args) ==  1 and args[0].isdigit():
        period = int(args[0])
    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
        reply_to_message_id=update.message.message_id,
    )
    trends = get_trend(pd.Timedelta(days=period))
    if period == 300:
        end = "des del primer registre"
    else:
        end = f"dels últims {period} dies"

    resps = [f"Pendent de la línia de tendència {end}"]
    up = "📈" 
    down = "📉" 
    for usr, m, n, intr, indx in trends:
        emoj = up if m > 0 else down
        plus = "+" if m > 0 else ""
        resp = f"{emoj} {usr}: {plus} {m * 10:.1f}%"
        resps.append(resp)

    resp = "\n".join(resps)
    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=resp,
    )
    
def unknown(update: Update, context: CallbackContext):
    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="No t'entec colega, ho deus haver escrit mal.",
        reply_to_message_id=update.message.message_id,
    )


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
    yesterday_handler = CommandHandler(["yesterday", "y"], yesterday)
    dispatcher.add_handler(yesterday_handler)
    summary_handler = CommandHandler("summary", summary)
    dispatcher.add_handler(summary_handler)
    reminder_handler = CommandHandler("reminder", reminder)
    dispatcher.add_handler(reminder_handler)
    rolling_avg_handler = CommandHandler("rolling_avg", rolling_avg)
    dispatcher.add_handler(rolling_avg_handler)
    trendline_handler = CommandHandler("trendline", trendline)
    dispatcher.add_handler(trendline_handler)
    st.session_state.Q = asyncio.Queue()
    ticker_handler = CommandHandler("ticker", partial(set_ticker, st.session_state.Q))
    dispatcher.add_handler(ticker_handler)
    unknown_handler = MessageHandler(Filters.command, unknown)
    dispatcher.add_handler(unknown_handler)
    return updater


@st.cache_resource
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


def get_trend(period: pd.Timedelta):
    df = _get_dataframe()
    df = df.loc[df.index > (df.index.max() - period)]
    users = list(df.columns)
    polys = []
    for usr in users:
        usrd = df[usr].dropna()
        dayn = (usrd.index - usrd.index.max()).days
        dayn -= dayn.min()
        vals = usrd.dt.total_seconds() // 60
        m, n = np.polyfit(dayn, vals, 1)
        intr = m * dayn + n
        polys.append((usr, m, n, intr, usrd.index))
    return polys


def generate_rolling_avg_plot(return_ax=False):
    df = _get_dataframe()
    users = list(df.columns)
    for usr in users:
        avg = []
        for w in df[usr].rolling(7):
            w.dropna(inplace=True)
            avg.append((w.sum() / len(w)).seconds // 60 if len(w) else np.nan)
        df[usr + "rollavg"] = avg
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m/%Y"))
    for usr in users:
        print(df.index, df[usr + "rollavg"])
        ax.plot(df.index, df[usr + "rollavg"], label=usr)
    ax.axhline(y=120, color="k", linestyle=":", linewidth=1, label="Objectiu")
    ax.legend()
    ax.set_xlabel("Dia")
    ax.set_ylabel("Minuts")
    fig.autofmt_xdate()
    fig.savefig("plot.png")
    if return_ax:
        return fig, ax
    return fig


def show_rolling_avg_plot():
    plot = generate_rolling_avg_plot()
    st.pyplot(plot)


def show_trend_lines():
    fig, ax = generate_rolling_avg_plot(return_ax=True)
    ax.set_prop_cycle(None)
    trend_lines = get_trend(pd.Timedelta(days=60))
    for _, m, n, intr, indx in trend_lines:
        ax.plot(indx, intr, linestyle=":")
        st.code((m, n))
    st.pyplot(fig)

    # st.code(trend_lines)

async def _ticker_task(dur):
    up = get_updater()
    up["tick_context"].bot.send_message(
        chat_id=up["update"].effective_chat.id,
        text="task begin",
    )
    while up["active"]:
        await asyncio.sleep(dur)
        up["tick_context"].bot.send_message(
        chat_id=up["tick_update"].effective_chat.id,
        text="TICKER",
        reply_to_message_id=up["tick_update"].message.message_id,
    )


@st.cache_resource
def ticker_task(dur=10):
    up = get_updater()
    up["tick_context"].bot.send_message(
        chat_id=up["update"].effective_chat.id,
        text="task prep",
    )
    return asyncio.create_task(_ticker_task(dur))


async def handle_queue():
    print("setting queu")
    print(list(st.session_state.items()))
    it = await st.session_state.Q.get()
    print("done")
    up = get_updater()
    up["tick_context"].bot.send_message(
        chat_id=up["update"].effective_chat.id,
        text="getting queue",
    )
    st.session_state.Q.task_done()
    up = get_updater()
    up["tick_update"] = it["update"]
    up["tick_context"] = it["context"]
    st.session_state.task = ticker_task()



async def main():
    st.title("Telegram bot dashboard")
    with st.sidebar:
        st.button("Start bot", on_click=start_telegram_bot)
        st.button("Stop bot", on_click=stop_bot)
        st.button("Restart bot", on_click=restart_bot)
        st.button("Print df", on_click=show_st_dataframe)
        st.button("Show rolling avg plot", on_click=show_rolling_avg_plot)
        st.button("Show trend lines", on_click=show_trend_lines)

    up = get_updater()
    st.markdown("## The bot is running" if up["active"] else "## Nothing running.")
    # st.session_state.task = asyncio.create_task(handle_queue())


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
