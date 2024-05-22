import pandas as pd
from datetime import datetime
import configparser

from calling import *
def check_scheduled_task(file_path,config):
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
    current_day = datetime.today().strftime('%A').upper()
    current_time = datetime.now().strftime('%H:%M')

    # Read Excel file for the current day's sheet
    df = pd.read_excel(file_path, usecols=columns, sheet_name=current_day, index_col=index)

    # Check if there are any tasks scheduled for the current time
    if 'CALL_TIME' in df.columns:
        column_list = df['CALL_TIME'].tolist()
        CALL_TIME_LIST = [time_obj.strftime('%H:%M') for time_obj in column_list]
        if current_time in CALL_TIME_LIST:
            logger.info(f"There Exist  Task for {current_time}")
            filter_df = df.iloc[CALL_TIME_LIST.index(current_time)]
            Message=filter_df['MESSAGE']
            calling_on_phone(account_sid=account_sid, auth_token=auth_token, Message=Message, to=to, from_=from_)

        else:
          logger.info("No task scheduled at the current time.")# No task scheduled for the current time

