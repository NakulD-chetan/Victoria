import requests
from googletrans import Translator
import datetime

from loguru import logger


def fetch_and_translate_quote():
    def fetch_random_quote():
        url = "https://api.quotable.io/random"
        response = requests.get(url)
        if response.status_code == 200:
            quote_data = response.json()
            return quote_data['content']
        else:
            return None

    def translate_to_hindi(text):
        translator = Translator()
        translation = translator.translate(text=text, src='en', dest='hi')
        return translation.text

    quote = fetch_random_quote()
    if quote:
        logger.info(quote)
        hindi_quote = translate_to_hindi(quote)
        return hindi_quote
    else:
        return "Error fetching quote."


def generate_motivational_message(no,message,quote, start_time, call_time, end_time):
    # English to Hindi day conversion
    days_in_hindi = {
        "Monday": "सोमवार",
        "Tuesday": "मंगलवार",
        "Wednesday": "बुधवार",
        "Thursday": "गुरुवार",
        "Friday": "शुक्रवार",
        "Saturday": "शनिवार",
        "Sunday": "रविवार"
    }
    hindi_numbers = {
        "1": "पहला",
        "2": "दूसरा",
        "3": "तीसरा",
        "4": "चौथा",
        "5": "पाँचवा",
        "6": "छठा",
        "7": "सातवा",
        "8": "आठवा",
        "9": "नौवा",
        "10": "दसवा",
        "11": "ग्यारहवा",
        "12": "बारहवा",
        "13": "तेरहवा",
        # Add more numbers as needed
    }

    # Get current day in Hindi
    current_day = datetime.datetime.now().strftime("%A")
    current_day_hindi = days_in_hindi.get(current_day, current_day)
    no=hindi_numbers.get(str(no), '0')# Default to English if not found

    # Get current hour
    current_hour = datetime.datetime.now().hour

    # Set the initial greeting based on the current hour
    if current_hour < 12:
        initial_greeting = "नमस्ते चेतन! सुप्रभात! तुम्हारा दिन शुभ हो"
    elif current_hour < 17:
        initial_greeting = "नमस्ते चेतन! शुभ दोपहर! तुम्हारा दिन शुभ हो"
    else:
        initial_greeting = "नमस्ते चेतन! शुभ संध्या! तुम्हारा दिन शुभ हो"

    # Define message template


    # Replace placeholders in the message with actual values
    modified_message = message.format(
        initial_greeting=initial_greeting,
        current_day_hindi=current_day_hindi,
        num=no,
        call_time=call_time,
        start_time=start_time,
        end_time=end_time,
        quote=quote,
    )

    return modified_message


def generate_gita_message(chapter_name,chapter_meaning,slok,slok_meaning,no,message,start_time,call_time,end_time):
    days_in_hindi = {
        "Monday": "सोमवार",
        "Tuesday": "मंगलवार",
        "Wednesday": "बुधवार",
        "Thursday": "गुरुवार",
        "Friday": "शुक्रवार",
        "Saturday": "शनिवार",
        "Sunday": "रविवार"
    }
    hindi_numbers = {
        "1": "पहला",
        "2": "दूसरा",
        "3": "तीसरा",
        "4": "चौथा",
        "5": "पाँचवा",
        "6": "छठा",
        "7": "सातवा",
        "8": "आठवा",
        "9": "नौवा",
        "10": "दसवा",
        "11": "ग्यारहवा",
        "12": "बारहवा",
        "13": "तेरहवा",
        # Add more numbers as needed
    }

    # Get current day in Hindi
    current_day = datetime.datetime.now().strftime("%A")
    current_day_hindi = days_in_hindi.get(current_day, current_day)
    no = hindi_numbers.get(str(no), '0')  # Default to English if not found
    current_hour = datetime.datetime.now().hour

    # Set the initial greeting based on the current hour
    if current_hour < 12:
        initial_greeting = "नमस्ते चेतन! सुप्रभात! तुम्हारा दिन शुभ हो"
    elif current_hour < 17:
        initial_greeting = "नमस्ते चेतन! शुभ दोपहर! तुम्हारा दिन शुभ हो"
    else:
        initial_greeting = "नमस्ते चेतन! शुभ संध्या! तुम्हारा दिन शुभ हो"

        modified_message = message.format(
            initial_greeting=initial_greeting,
            current_day_hindi=current_day_hindi,
            num=no,
            call_time=call_time,
            start_time=start_time,
            end_time=end_time,
            chapter_name=chapter_name,
            chapter_meaning=chapter_meaning,
            slok=slok,
            slok_meaning=slok_meaning,
        )
        return modified_message



