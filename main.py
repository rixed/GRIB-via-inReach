import emailfunctions
from base64 import urlsafe_b64decode, urlsafe_b64encode
import time
from datetime import datetime
import xarray as xr
import cfgrib
import numpy as np
import pandas as pd
import time
from codec import encode

import os
import re

LIST_OF_PREVIOUS_MESSAGES_FILE_LOCATION = os.environ.get("LIST_OF_PREVIOUS_MESSAGES_FILE_LOCATION", "/tmp/GRIB-via-inReach")
YOUR_EMAIL = os.environ.get("YOUR_EMAIL", "foo@bar.baz")


def inreachReply(url, domain_prefix, message_str):
    # This uses the requests module to send a spoofed response to Garmin. I found no trouble reusing the MessageId over and over again but I do not know if there are risks with this.
    # I tried to use the same GUID from the specific incoming garmin email.
    import requests

    cookies = {
        'BrowsingMode': 'Desktop',
    }

    headers = {
        'authority': f"{domain_prefix}explore.garmin.com",
        'accept': '*/*',
        'accept-language': 'en-US,en;q=0.9',
        'cache-control': 'no-cache',
        'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'cookie': 'BrowsingMode=Desktop',
        'dnt': '1',
        'origin': f"https://{domain_prefix}explore.garmin.com",
        'pragma': 'no-cache',
        'referer': url,
        'sec-ch-ua': '"Chromium";v="106", "Not;A=Brand";v="99", "Google Chrome";v="106.0.5249.119"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Linux"',
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

    print(f"inreachReply: posting with headers {headers} and data {data}...", flush=True)
    r = requests.post(f"https://{domain_prefix}explore.garmin.com/TextMessage/TxtMsg", cookies=cookies, headers=headers, data=data)
    if r.status_code != 200:
        print(f"Could not send! response code={r.status_code}, headers={r.headers}, history={r.history}, data was {data}", flush=True)
    else:
        print('Sent', flush=True)
    return r

def send_sms_via_url(url, domain_prefix):
    def send_sms(part):
        print(f"Sending to {url} ({domain_prefix}):\n{part}", flush=True)
        res = inreachReply(url, domain_prefix, part)
        print(f"sent!", flush=True)
        time.sleep(10)  # Give inReach some time to send the SMS
        return (res.status_code == 200)
    return send_sms


GARMIN_URL_RE = re.compile("https://([a-z]*\.)?explore.garmin.com")

def answerService(message_id):
    print(f"answerService {message_id}", flush=True)
    msg = service.users().messages().get(userId='me', id=message_id).execute()
    msg_text = urlsafe_b64decode(msg['payload']['body']['data']).decode().split('\r')[0].lower()
    print(f"text = {msg_text}", flush=True)
    url = None
    domain_prefix = None
    full_msg = urlsafe_b64decode(msg['payload']['body']['data']).decode()
    for line in full_msg.split('\n'):
        m = GARMIN_URL_RE.search(line)
        if m is not None:
            url = line.replace('\r', '')
            domain_prefix = m.group(1)
            break
    if url is None:
        print(f"Cannot find GARMIN URL in:\n{full_msg}\n", flush=True)
        return
    else:
        print(f"Will send using url:{url} and domain_prefix:{domain_prefix}")

    if msg_text[:5] == 'ecmwf' or msg_text[:3] == 'gfs': # Only allows for ECMWF or GFS model
        emailfunctions.send_message(service, "query@saildocs.com", message_id, "send " + msg_text) # Sends message to saildocs according to their formatting.
        time_sent = datetime.utcnow()
        valid_response = False

        for i in range(60): # Waits for reply and makes sure reply received aligns with request (there's probably a better way to do this).
            print("Waiting for answer...")
            time.sleep(10)
            last_responses = emailfunctions.search_messages(service, "from:query-reply@saildocs.com")
            if len(last_responses) > 0:
                    last_response = last_responses[0]
                    header = service.users().messages().get(userId='me', id=last_response['id']).execute()['payload']['headers']
                    print(f"header = {header}")
                    time_received = pd.to_datetime(header[-1]['value'].split('(UTC)')[0])
                    if time_received > time_sent:
                        print("Found response!")
                        valid_response = True
                        break

        if valid_response:
            try:
                grib_path = emailfunctions.GetAttachments(service, last_response['id'])
            except:
                inreachReply(url, domain_prefix, "Could not download attachment")
                return

            print("Found attachment, encoding it...")
            encode(grib_path, send_sms_via_url(url, domain_prefix))

        else:
            inreachReply(url, domain_prefix, "Saildocs timeout")
            return False
    else:
        inreachReply(url, domain_prefix, "Invalid model")
        return False


def checkMail():
    ### This function checks the email inbox for Garmin inReach messages. I tried to account for multiple messages.
    global service
    service = emailfunctions.gmail_authenticate()
    results = emailfunctions.search_messages(service, "from:no.reply.inreach@garmin.com")
    print(f"{len(results)} results", flush=True)

    inreach_msgs = []
    for result in results:
        inreach_msgs.append(result['id'])

    with open(LIST_OF_PREVIOUS_MESSAGES_FILE_LOCATION, 'a+t') as f: # This is a running list of previous inReach messages that have already been responded to.
        f.seek(0)
        previous = f.read()

        unanswered = [message for message in inreach_msgs if message not in previous.split('\n')]
        print(f"unanswered={unanswered}")
        for message_id in unanswered:
            try:
                answerService(message_id)
            except Exception as e:
                print(e, flush=True)
            # Whether answering was a success or failure, add message to list.
            f.write(message_id + '\n')


print('Starting loop')
while(True):
    print('Checking...', flush=True)
    try:
        checkMail()
    except TimeoutError:
        print("Timeout! Let's pause for a bit...\n")
        time.sleep(500)
    time.sleep(240)
