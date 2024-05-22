import time
from datetime import datetime
from loguru import logger
from twilio.rest import Client
import pandas as pd
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
    # Get current day and time

    # Read Excel file for the current day's sheet
    df = pd.read_excel(file_path, usecols=columns, sheet_name=current_day, index_col=index)

    # Check if there are any tasks scheduled for the current time
    if 'CALL_TIME' in df.columns:
        column_list = df['CALL_TIME'].tolist()
        CALL_TIME_LIST = [time_obj.strftime('%H:%M') for time_obj in column_list]
        while True:
            current_time=datetime.now().strftime('%H:%M')
            current_day = datetime.today().strftime('%A').upper()
            if current_time in CALL_TIME_LIST:
                logger.info(f"There Exist  Task for {current_time}")
                filter_df = df.iloc[CALL_TIME_LIST.index(current_time)]
                Message = filter_df['MESSAGE']
                calling_on_phone(account_sid=account_sid, auth_token=auth_token, Message=Message, to=to, from_=from_)

            else:
                logger.info(
                    f"No task scheduled for the this time,and day-{current_time, current_day}")  # No task scheduled for the current time

            time.sleep(60)


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
