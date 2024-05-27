from configparser import ConfigParser

from flask import Flask, request
from twilio.twiml.voice_response import Gather, VoiceResponse
from twilio.rest import Client

app = Flask(__name__)

config= ConfigParser()
config.read('config.ini')
# Set up your Twilio credentials
account_sid = config['Twilio']['account_sid']
auth_token = config['Twilio']['auth_token']
client = Client(account_sid, auth_token)

# Function to make a call and gather user input
def make_call_and_gather(to_phone_number, message,from_):
    call = client.calls.create(
        to=to_phone_number,
        from_=from_,
        twiml=f'<Response><Say>{message}</Say><Gather numDigits="1" action="/gather_callback"></Gather></Response>'
    )

@app.route('/gather_callback', methods=['POST'])
def gather_callback():
    # Get the digit entered by the user
    digit_pressed = request.values.get('Digits', None)
    if digit_pressed:
        print("User pressed:", digit_pressed)
    else:
        print("No digit pressed")
    return str(VoiceResponse())

if __name__ == '__main__':
    # Make a call and gather user input when the script is run
    make_call_and_gather('TO_PHONE_NUMBER', 'Hello! Please enter a digit after the beep.')
    app.run(debug=True)




url = config['Twilio']['url']
to = config['Twilio']['to_phone']
from_ = config['Twilio']['from_phone']
make_call_and_gather(to,"Hello! Please enter a digit after the beep ",from_)