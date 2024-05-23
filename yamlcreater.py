from configparser import ConfigParser
from datetime import datetime

import pandas as pd
import pytz
from loguru import logger


def generate_workflow(call_time_list):

    cron_schedules = [convert_ist_to_utc(time_str) for time_str in call_time_list]

    workflow = """name: Dynamic Schedule Python Script\non:\n"""
    workflow += "  schedule:\n"
    for cron in cron_schedules:
        workflow += f"    - cron: '{cron}'\n"

    workflow += """\njobs:\n run-script:
      runs-on: ubuntu-latest

      steps:
        - name: Checkout repository
          uses: actions/checkout@v2

        - name: Set up Python
          uses: actions/setup-python@v2
          with:
            python-version: '3.x'

        - name: Install dependencies
          run: |
            if [ -f requirements.txt ]; then pip install -r requirements.txt; fi

        - name: Run Python script
          run: python main.py
    """
    return workflow

def write_workflow_to_file(workflow_content):
    with open('.github/workflows/dynamic_schedule.yml', 'w') as f:
        f.write(workflow_content)
def convert_ist_to_utc(ist_time_str):
    ist = pytz.timezone('Asia/Kolkata')
    utc = pytz.utc
    ist_time = datetime.strptime(ist_time_str, '%H:%M')
    ist_time = ist.localize(ist_time)
    utc_time = ist_time.astimezone(utc)
    return utc_time.strftime('%M %H * * *')
def modify_yaml_file(file_path,yaml_config):
    logger.info("Reading Data From Excel File")
    columns = yaml_config['EXCEL']['columns'].split(",")
    index = columns[0]
    local_tz = pytz.timezone('Asia/Kolkata')
    utc_time = datetime.now(pytz.utc)
    # Convert UTC time to local time
    local_time = utc_time.astimezone(local_tz)
    current_time = local_time.strftime('%H:%M')
    current_day = local_time.strftime('%A').upper()
    # Read Excel file for the current day's sheet
    df = pd.read_excel(file_path, usecols=columns, sheet_name=current_day, index_col=index)

    # Check if there are any tasks scheduled for the current time
    if 'CALL_TIME' in df.columns:
        column_list = df['CALL_TIME'].tolist()
        CALL_TIME_LIST = [time_obj.strftime('%H:%M') for time_obj in column_list]
        return CALL_TIME_LIST

    else:
        logger.info(f"No CALL_TIME column in Excel File for{current_day}")

yaml_config = ConfigParser()
yaml_config.read('config.ini')
call_time_list=modify_yaml_file(yaml_config['EXCEL']['path'], yaml_config)
write_workflow_to_file(generate_workflow(call_time_list))

