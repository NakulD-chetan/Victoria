from configparser import ConfigParser
from datetime import datetime

import pandas as pd
import pytz
from loguru import logger


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




yaml_config = ConfigParser()
yaml_config.read('config.ini')
modify_yaml_file(yaml_config['EXCEL']['path'], yaml_config)
