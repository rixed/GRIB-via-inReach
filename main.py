print('Starting import', flush=True)
import emailfunctions
from base64 import urlsafe_b64decode, urlsafe_b64encode
import time
from datetime import datetime
import xarray as xr
import cfgrib
import pandas as pd
import numpy as np
import time
from codec import encode

print('Import finished', flush=True)

LIST_OF_PREVIOUS_MESSAGES_FILE_LOCATION = ""
YOUR_EMAIL = ""


def inreachReply(url, message_str):
    # This uses the requests module to send a spoofed response to Garmin. I found no trouble reusing the MessageId over and over again but I do not know if there are risks with this.
    # I tried to use the same GUID from the specific incoming garmin email.
    import requests

    cookies = {
        'BrowsingMode': 'Desktop',
    }

    headers = {
        'authority': 'explore.garmin.com',
        'accept': '*/*',
        'accept-language': 'en-US,en;q=0.9',
        'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
        # 'cookie': 'BrowsingMode=Desktop',
        'origin': 'https://explore.garmin.com',
        'referer': url,
        'sec-ch-ua': '"Chromium";v="106", "Not;A=Brand";v="99", "Google Chrome";v="106.0.5249.119"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36',
        'x-requested-with': 'XMLHttpRequest',
    }

    data = {
        'ReplyAddress': YOUR_EMAIL,
        'ReplyMessage': message_str,
        'MessageId': '479947347',
        'Guid': url.split('extId=')[1].split('&adr')[0],
    }

    response = requests.post('https://explore.garmin.com/TextMessage/TxtMsg', cookies=cookies, headers=headers, data=data)
    if response.status_code != 200:
        print('Could not send!', flush=True)
    else:
        print('Sent', flush=True)
    return response


def send_sms_via_url(url):
    def send_sms(part):
        res = inreachReply(url, part)
        time.sleep(10)  # Give inReach some time to send the SMS
        return (res.status_code == 200)
    return send_sms


def answerService(message_id):
    msg = service.users().messages().get(userId='me', id=message_id).execute()
    msg_text = urlsafe_b64decode(msg['payload']['body']['data']).decode().split('\r')[0].lower()
    url = [x.replace('\r','') for x in urlsafe_b64decode(msg['payload']['body']['data']).decode().split('\n') if 'https://explore.garmin.com' in x][0] # Grabs the unique Garmin URL for answering.

    if msg_text[:5] == 'ecmwf' or msg_text[:3] == 'gfs': # Only allows for ECMWF or GFS model
        emailfunctions.send_message(service, "query@saildocs.com", "", "send " + msg_text) # Sends message to saildocs according to their formatting.
        time_sent = datetime.utcnow()
        valid_response = False

        for i in range(60): # Waits for reply and makes sure reply received aligns with request (there's probably a better way to do this).
            time.sleep(10)
            last_response = emailfunctions.search_messages(service,"query-reply@saildocs.com")[0]
            time_received = pd.to_datetime(service.users().messages().get(userId='me', id=last_response['id']).execute()['payload']['headers'][-1]['value'].split('(UTC)')[0])
            if time_received > time_sent:
                valid_response = True
                break

        if valid_response:
            try:
                grib_path = emailfunctions.GetAttachments(service, last_response['id'])
            except:
                inreachReply(url, "Could not download attachment")
                return

            encode(grib_path, send_sms_via_url(url))

        else:
            inreachReply(url, "Saildocs timeout")
            return False
    else:
        inreachReply(url, "Invalid model")
        return False


def checkMail():
    ### This function checks the email inbox for Garmin inReach messages. I tried to account for multiple messages.
    global service
    service = emailfunctions.gmail_authenticate()
    results = emailfunctions.search_messages(service,"no.reply.inreach@garmin.com")

    inreach_msgs = []
    for result in results:
        inreach_msgs.append(result['id'])

    with open(LIST_OF_PREVIOUS_MESSAGES_FILE_LOCATION) as f: # This is a running list of previous inReach messages that have already been responded to.
        previous = f.read()

    unanswered = [message for message in inreach_msgs if message not in previous.split('\n')]
    for message_id in unanswered:
        try:
            answerService(message_id)
        except Exception as e:
            print(e, flush=True)
        with open(LIST_OF_PREVIOUS_MESSAGES_FILE_LOCATION, 'a') as file: # Whether answering was a success or failure, add message to list.
            file.write('\n'+message_id)


print('Starting loop')
while(True):
    time.sleep(60)
    print('Checking...', flush=True)
    checkMail()
    time.sleep(240)
