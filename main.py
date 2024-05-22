# Download the helper library from https://www.twilio.com/docs/python/install
from loguru import logger
import os
import coloredlogs
from twilio.rest import Client
from configparser import ConfigParser
import os
from logging import *
from speach import *
from calling import *
from excel import *

logger.info("------------------------------------------------------------------------------------------------------")
logger.info("<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<{------VICTORIA PROGRAM STARTED------}>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
logger.info("------------------------------------------------------------------------------------------------------")
config=ConfigParser()
config.read('config.ini')
logger.info("Reading Configuration file")

logger.info("Reading Data From Confugration File is Done ")
check_scheduled_task(config['EXCEL']['path'],config)
# audio_content = convert_text_to_speech(hindi_text, config['TEXT_TO_SPEECH']['voice_id'], config['TEXT_TO_SPEECH']['api_key'], output_file)







