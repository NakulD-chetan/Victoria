from configparser import ConfigParser

from twilio.rest import Client
import os

def send_sms(to, message_body,config):
    # Your Account SID and Auth Token from twilio.com/console
    account_sid = config['Twilio']['account_sid']
    auth_token = config['Twilio']['auth_token']
    from_phone = config['Twilio']['from_phone']

    if not account_sid or not auth_token:
        raise ValueError("Twilio credentials are not set in environment variables")

    client = Client(account_sid, auth_token)

    message = client.messages.create(
        body=message_body,
        from_=from_phone,  # Your Twilio phone number
        to=to
    )

    print(f"Message sent. SID: {message.sid}")

config=ConfigParser()
config.read('config.ini')
send_sms(config['Twilio']['to_phone'], 'THis is First Message',config)