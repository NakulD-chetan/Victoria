from loguru import logger
from twilio.rest import Client

import logging
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