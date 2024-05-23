import time
from datetime import datetime, timedelta
from loguru import logger
from twilio.rest import Client
import pandas as pd
import pytz
from configparser import ConfigParser


def check_scheduled_task(file_path, config):
    # Read configuration
    logger.info("Reading Data From Excel File")
    columns = config['EXCEL']['columns'].split(",")
    index = columns[0]
    account_sid = config['Twilio']['account_sid']
    auth_token = config['Twilio']['auth_token']
    url = config['Twilio']['url']
    to = config['Twilio']['to_phone']
    from_ = config['Twilio']['from_phone']
    local_tz = pytz.timezone('Asia/Kolkata')
    utc_time = datetime.now(pytz.utc)
    # Convert UTC time to local time
    local_time = utc_time.astimezone(local_tz)
    current_time_data = local_time.strftime('%H:%M')
    current_day = local_time.strftime('%A').upper()
    # Read Excel file for the current day's sheet
    df = pd.read_excel(file_path, usecols=columns, sheet_name=current_day, index_col=index)

    # Check if there are any tasks scheduled for the current time
    if 'CALL_TIME' in df.columns:
        column_list = df['CALL_TIME'].tolist()
        CALL_TIME_LIST = [time_obj.strftime('%H:%M') for time_obj in column_list]
        current_time = datetime.strptime(current_time_data, "%H:%M")
        time_margin = timedelta(minutes=13)

        call_scheduled = False
        for call_time_str in CALL_TIME_LIST:
            call_time = datetime.strptime(call_time_str, "%H:%M")
            # logger.info(f"{call_time,current_time,call_time - time_margin,call_time + time_margin}")

            if call_time - time_margin <= current_time <= call_time + time_margin:
                logger.info(f"There exists a task for {current_time.strftime('%H:%M')}")
                filter_df = df.iloc[CALL_TIME_LIST.index(call_time_str)]
                Message = filter_df['MESSAGE']
                calling_on_phone(account_sid=account_sid, auth_token=auth_token, Message=Message, to=to, from_=from_)
                call_scheduled = True
                break

        if not call_scheduled:
            logger.info(f"No task scheduled for this time and day - {current_time_data}, {current_day}")



def calling_on_phone(Message, account_sid, auth_token, to, from_):
    logger.info(f"Calling process initiated to {to} from Victoria")
    client = Client(username=account_sid, password=auth_token)
    twiml = f'<Response><Say language="hi-IN">{Message}</Say></Response>'
    call = client.calls.create(
        twiml=twiml,
        to=to,
        from_=from_,
    )

    logger.info("Be Patient it takes Some Seconds")


logger.info("------------------------------------------------------------------------------------------------------")
logger.info("<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<{------VICTORIA PROGRAM STARTED------}>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
logger.info("------------------------------------------------------------------------------------------------------")
config = ConfigParser()
config.read('config.ini')
logger.info("Reading Configuration file")

logger.info("Reading Data From Confugration File is Done ")
check_scheduled_task(config['EXCEL']['path'], config)
