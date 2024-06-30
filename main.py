import time
from datetime import datetime, timedelta
import os
import requests
from loguru import logger
from twilio.rest import Client
import pandas as pd
import pytz
from configparser import ConfigParser

from bhagvad import get_gita_slokh_with_name_summary
from quotes import fetch_and_translate_quote, generate_motivational_message, generate_gita_message


def get_task_info_by_call_time(data, call_time):
    # Function to convert time string to minutes for easy comparison
    def time_to_minutes(time_str):
        hours, minutes = map(int, time_str.split(':'))
        return hours * 60 + minutes

    # Convert the input call time to minutes
    call_time_minutes = time_to_minutes(call_time)
    last_task=data[-1]['fields']
    if last_task is None:
        last_task = None



    for task in data:
        task_fields = task['fields']
        task_call_time = task_fields['CALL_TIME']

        # Convert the task's call time to minutes
        task_call_time_minutes = time_to_minutes(task_call_time)

        # Check if the task's call time matches the input call time
        if task_call_time_minutes == call_time_minutes:
            return {
                'MESSAGE': task_fields['MESSAGE'],
                'NO': task_fields['NO'],
                'TASK_NAME': task_fields['TASK_NAME'],
                'CALL_TIME': task_fields['CALL_TIME'],
                'START_TIME': task_fields['START_TIME'],
                'END_TIME': task_fields['END_TIME']
            },{
                'MESSAGE': last_task['MESSAGE'],
                'NO': last_task['NO'],
                'TASK_NAME': last_task['TASK_NAME'],
                'CALL_TIME': last_task['CALL_TIME'],
                'START_TIME': last_task['START_TIME'],
                'END_TIME': last_task['END_TIME']
            }

    # If no task matches the given call time
    return None,last_task






def fetch_airtable_data(config,table_name,call_time_input):
    logger.info("Loading airtable config data from json")
    api_key=os.getenv('API_KEY')
    base_id = os.getenv('BASE_ID')
    # logger.info(f"table_name = {table_name}")
    logger.info("Data Loaded Successfully from Json")

    url = f"https://api.airtable.com/v0/{base_id}/{table_name}"
    headers = {
        "Authorization": f"Bearer {api_key}"
    }
    logger.info("Fetching Airtable Data through Internet Connection")
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        try:
            logger.info("Data Successfully Fetched From Airtable through Internet Connection")
            records = response.json().get('records', [])
            sorted_records = sorted(records, key=lambda x: x['fields']['NO'])

            result,last_task = get_task_info_by_call_time(sorted_records, call_time_input)
            return result,last_task
        except Exception as e:
            logger.error(f"Error Occure in fetch_airtable_data function-{e}")
            return None,None


    else:
        print(f"Failed to fetch data. Status code: {response.status_code}")
        return None,None

def check_scheduled_task(config):
    # Read configuration
    logger.info("Reading Data From Excel File")
    columns = config['EXCEL']['columns'].split(",")
    index = columns[0]
    account_sid = os.getenv('ACCOUNT_SID')
    logger.info(account_sid)

    auth_token = os.getenv('AUTH_TOKEN')
    logger.info(auth_token)
    url = os.getenv('URL')
    to = os.getenv('TO_PHONE')
    from_ = os.getenv('FROM_PHONE')
    while True:
        local_tz = pytz.timezone('Asia/Kolkata')
        utc_time = datetime.now(pytz.utc)
        # Convert UTC time to local time
        local_time = utc_time.astimezone(local_tz)
        current_time_data = local_time.strftime('%H:%M')
        current_day = local_time.strftime('%A').upper()
        # Read Excel file for the current day's sheet
        data,last_data = fetch_airtable_data(config, table_name='SATURDAY',call_time_input=current_time_data )

        if data is None:
            logger.info(f"No task scheduled for this time and day - {current_time_data}, {current_day}")
        else:
            if last_data.get("CALL_TIME") == current_time_data:
                name_of_ch,meaning_of_ch,sanskrit_slokh,meaning_of_slok=get_gita_slokh_with_name_summary()
                TASK_NAME = last_data.get("TASK_NAME")
                logger.info(f"Task Name: {TASK_NAME}")
                MESSAGE = last_data.get("MESSAGE")
                CALL_TIME = last_data.get("CALL_TIME")
                NO = last_data.get("NO")
                START_TIME = last_data.get("START_TIME")
                END_TIME = last_data.get("END_TIME")
                modified_message = generate_gita_message(
                    message=MESSAGE,
                    end_time=END_TIME,
                    call_time=CALL_TIME,
                    start_time=START_TIME,
                    no=NO,
                    slok_meaning=meaning_of_slok,
                    slok=sanskrit_slokh,
                    chapter_name=name_of_ch,
                    chapter_meaning=meaning_of_ch
                )
                logger.info(f"Modified Message: {modified_message}")

            else:
                MESSAGE = data.get("MESSAGE")
                try:
                 quote =fetch_and_translate_quote()
                except Exception as e:
                    logger.error(e)
                TASK_NAME = data.get("TASK_NAME")
                logger.info("Task Name: {}".format(TASK_NAME))
                CALL_TIME = data.get("CALL_TIME")
                NO = data.get("NO")
                START_TIME = data.get("START_TIME")
                END_TIME = data.get("END_TIME")
                modified_message = generate_motivational_message(NO,MESSAGE,quote, START_TIME, CALL_TIME, END_TIME)
                logger.info(f"Modified Message: {modified_message}")
            logger.info(f"There exists a task for {current_time_data}")
            calling_on_phone(account_sid=account_sid, auth_token=auth_token, Message=modified_message, to=to, from_=from_)
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
check_scheduled_task(config)


