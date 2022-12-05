import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import date

from telegram.ext import Updater
import logging
from telegram import Update
from telegram.ext import CallbackContext
from telegram.ext import CommandHandler


from sqlalchemy.engine import create_engine

st.title("Telegram bot dashboard")

HELP = "commands /start, /register, /yesterday <hh> <mm>"

st.markdown("## The bot is running" if "updater" in st.session_state else "## Nothing running.")


def read_db():
    db = pd.read_csv("db.csv")
    st.session_state.db = db


def write_db():
    gs_url = st.secrets["gs_url"]


    engine = create_engine(
        "gsheets://",
        catalog={
            "simple_sheet": (
                "https://docs.google.com/spreadsheets/d/1_rN3lm0R_bU3NemO0s9pbFkY5LQPcuy1pscv8ZXPtg8/edit#gid=774535750"
            ),
        },
    )
    connection = engine.connect()
    for row in connection.execute("SELECT * FROM simple_sheet"):
        print(row)
        st.write(row)


def register_user(update: Update, context: CallbackContext):
    user = update.message.from_user
    username = user.username or user.first_name or user.name or user.full_name or user.id
    username = username.lower()
    try: 
        if not username.isalpha() or len(username) > 20:
            resp = "Invalid username, only <20 chars and only letters allowed"
        elif Path(f"{username}.csv").is_file():
            resp = "Ja estas registrat cabron."
        else:
            db_user = pd.DataFrame({"date": [], "value": []}).set_index("date")
            db_user.to_csv(f"{username}.csv")
            resp = f"Hola {username}, benvingut."
    except AttributeError as e:
        context.bot.send_message(chat_id=update.effective_chat.id, text="Algo va mal...")
        raise e
    context.bot.send_message(chat_id=update.effective_chat.id, text=resp)

def summary(update: Update, context: CallbackContext):
    user = update.message.from_user
    username = user.username or user.first_name or user.name or user.full_name or user.id
    username = username.lower()
    try:
        user_db = Path(f"{username}.csv")
        if not user_db.is_file():
            resp = "User not registered. Write /register to do so."
            context.bot.send_message(chat_id=update.effective_chat.id, text=resp)
            return
        db_user = pd.read_csv(user_db, index_col="date", parse_dates=[0], infer_datetime_format=True) 
        val = pd.to_timedelta(db_user["value"])
        total, high, low, avg = val.sum().components, val.max().components, val.min().components, val.mean().components
        t = f"En total has passat {total.days} dies, {total.hours} hores i {total.minutes} minuts mirant el mobil."
        h = f"El teu record en un dia es de {high.hours} hores i {high.minutes} minuts."
        l = f"I el minim que has aconseguit es de {low.hours} hores i {low.minutes} minuts."
        a = f"La teva mitjana diaria es de {avg.hours} hores i {avg.minutes} minuts."
        for resp in [t,h,l,a]:
            context.bot.send_message(chat_id=update.effective_chat.id, text=resp)
    except AttributeError as e:
        context.bot.send_message(chat_id=update.effective_chat.id, text="Algo va mal...")
        raise e



def start(update: Update, context: CallbackContext):
    user = update.message.from_user
    username = user.username or user.first_name or user.name or user.full_name or user.id
    username = username.lower()
    resp = f"Fa pal escriure descripcio, hola {username}, i tal. Commandes son: " + HELP
    context.bot.send_message(
        chat_id=update.effective_chat.id, text=resp
    )


def reminder(update: Update, context: CallbackContext):
    users = Path("./").glob("*.csv")
    done = []
    pending = []
    for user_db_path in users:
        db_user = pd.read_csv(user_db_path, index_col="date", parse_dates=[0], infer_datetime_format=True) 
        username = '@' + user_db_path.stem
        if pd.Timestamp(date.today() - pd.Timedelta(days=1)) in db_user.index:
            done.append(username)
        else:
            pending.append(username)
    if not done:
        message = "Ningu ha marcat encara el seu us d'ahir"
    elif not pending:
        message = "Tots els usuaris han marcat l'us d'ahir"
    elif len(pending) == 1:
        message = f"Tots els usuaris han marcat l'us d'ahir, excepte {pending[0]}, espavila."
    else:
        message = f"{', '.join(done)} ja han marcat, falten {', '.join(pending)}."
    context.bot.send_message(chat_id=update.effective_chat.id, text=message)
    

def yesterday(update: Update, context: CallbackContext):
    user = update.message.from_user
    username = user.username or user.first_name or user.name or user.full_name or user.id
    username = username.lower()
    value = context.args
    user_db = Path(f"{username}.csv")
    if not user_db.is_file():
        resp = "User not registered. Write /register to do so."
    if len(value) != 2 or not all([v.isdigit() and len(v) == 2 for v in value]):
        resp = "Commanda en mal format. Escriu: '/yesterday hh mm' (hours minutes)"
    else:
        try:
            db_user = pd.read_csv(user_db, index_col="date", parse_dates=[0], infer_datetime_format=True) 
            delta  = pd.Timedelta(hours=int(value[0]), minutes=int(value[1]))
            db_user.loc[pd.Timestamp(date.today() - pd.Timedelta(days=1))] = delta
            db_user.to_csv(user_db)
            resp = f"M'apunto que ahir vas passar {value[0]} hores i {value[1]} minuts."
        except ValueError:
            resp = f"Something went wrong. try again later (I'm still building this!)"
    
    context.bot.send_message(chat_id=update.effective_chat.id, text=resp)
    reminder(update, context)


def start_telegram_bot():
    if "udpater" in st.session_state:
        st.text("already running")
        return

    token = st.secrets["BOT_TOKEN"]
    st.session_state.updater = Updater(
        token=token, use_context=True
    )
    updater = st.session_state.updater
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


def stop_bot():
    if "updater" not in st.session_state:
        print("nothing is running")
        return

    ret = st.session_state.updater.stop()
    print(ret)
    del st.session_state["updater"]


st.button("Start bot", on_click=start_telegram_bot)
st.button("Stop bot", on_click=stop_bot)
st.button("Write db", on_click=write_db)
