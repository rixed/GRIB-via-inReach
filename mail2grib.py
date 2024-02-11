import argparse
from codec import encode, just_print
from datetime import datetime, timedelta
from imap_tools import MailBox, AND
import json
import logging
import os
import pathlib
import random
import re
import requests
from smtplib import SMTP
import time
import traceback


ATTACHMENTS_PATH = os.environ.get("ATTACHMENTS_PATH", "/tmp/GRIB-via-inReach/attachments") # Where you want to save attachment files.


def inreachReply(mail_conf, url, domain_prefix, message_str):
    """
    Use the URL provided by Garmin to message the sailor
    """
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
        'ReplyAddress': mail_conf['email'],
        'ReplyMessage': message_str,
        'MessageId': str(random.getrandbits(64)),
        'Guid': url.split('extId=')[1].split('&adr')[0],
    }

    logging.info("Posting a SMS...")
    r = requests.post(f"https://{domain_prefix}explore.garmin.com/TextMessage/TxtMsg", cookies=cookies, headers=headers, data=data)
    if r.status_code != 200:
        logging.error(f"...COULD NOT SEND! RESPONSE CODE={r.status_code}")
    else:
        logging.info('...Sent!')
    return r


def send_sms_via_url(mail_conf, url, domain_prefix):
    def send_sms(part):
        logging.info(f"Sending to {url} ({domain_prefix}):\n{part}")
        res = inreachReply(mail_conf, url, domain_prefix, part)
        time.sleep(10)  # Give inReach some time to send the SMS
        return (res.status_code == 200)
    return send_sms


def send_message(mail_conf, dest, text):
    msg_id = str(random.getrandbits(64))
    logging.info(f"...Sending an email to {dest} with id {msg_id}")
    headers = [
        f"From: {mail_conf['email']}",
        f"To: {dest}",
        "Subject: mto request",
        f"Message-Id: {msg_id}",
    ]
    text = "\r\n".join(headers) + "\r\n\r\n" + text
    with SMTP(host=mail_conf['smtp-host'], port=mail_conf['smtp-port']) as smtp:
        smtp.starttls()
        smtp.login(mail_conf['username'], mail_conf['password'])
        smtp.sendmail(mail_conf['email'], dest, text)
        smtp.quit()
    return msg_id


GARMIN_URL_RE = re.compile("https://([a-z]*\.)?explore.garmin.com")

def handle_weather_request(state, mail_conf, msg):
    """
    Request a weather forecast on behalf of that sailor.
    Save the original request so we can forward the weather forecast when we receive it.
    """
    req = {}
    lines = list(filter(lambda s: len(s) > 0, [ line.strip() for line in msg.text.split('\r') ]))
    for line in lines:
        m = GARMIN_URL_RE.search(line)
        if m is not None:
            req['url'] = line.strip()
            req['domain_prefix'] = m.group(1)
            break

    if 'url' not in req:
        logging.error(f"...CANNOT FIND GARMIN URL IN:\n{msg.text}\n")
        return

    logging.info(f"...Will send using url:{req['url']} and domain_prefix:{req['domain_prefix']}")

    # If we could find the URL there is at least one line:
    first_line = lines[0]
    # Only allows for ECMWF or GFS model:
    if first_line[:5] == 'ecmwf' or first_line[:3] == 'gfs':
        # Sends message to saildocs according to their formatting:
        req['message-id'] = send_message(mail_conf, "query@saildocs.com", "send " + first_line)
        req['request'] = first_line
        req['time_sent'] = str(datetime.utcnow())
        state.append(req)
    else:
        print(f"...CANNOT FIND PROPER WEATHER REQUEST IN '{first_line}', SENDING BACK AN ERROR MESSAGE!", flush=True)
        inreachReply(mail_conf, req['url'], req['domain_prefix'], f"""
Cannot make sense of the forecast request. :-(
The forecasst request must be on the first line and look something like:
  ecmwf:25n,41n,29w,009w|2,2|12,24,36,48|wind

Your first line was:
  {first_line}
""")

    return state


def forward_forecast(state, mail_conf, request, time_recvd, grib_path):
    """
    Forward that grib file to each sailor who wanted it, and remove
    those requests from the state.
    """
    to_send = set()
    new_state = []
    for req in state:
        if req['request'] == request:
            # TODO: once we trust the dates, don't send if req['time_sent'] > time_recvd
            to_send.add((req['url'], req['domain_prefix']))
        else:
            logging.debug(f"...not for this sailor: {req['request']} != {request}")
            new_state.append(req)

    logging.info(f"...Forward the attachment to {len(to_send)} sailors!")
    for url, domain_prefix in to_send:
        encode(grib_path, send_sms_via_url(mail_conf, url, domain_prefix))

    return new_state


def handle_weather_answer(state, mail_conf, msg):
    """
    Get the grib file from the attachment and the request from the
    subject, and answer all pending queries waiting for that forecast
    (once per url).
    """
    # Start by extracting the actual request from the main body of the message:
    request = None
    for line in msg.text.split('\r'):
        line = line.strip()
        if line.startswith('request code: '):
            request = line[14:]
            logging.info(f"...Found original forecast request to be {request}")
    if request is None:
        logging.error(f"CANNOT FIND ORIGINAL REQUEST FROM:\n{msg.text}\n")
        return state

    time_recvd = msg.date
    processed = False
    for att in msg.attachments:
        fname, ext = os.path.splitext(att.filename)
        logging.info(f"...Found an attachment: {att.filename}")
        fname = os.path.basename(att.filename)
        if ext != '.grb':
            continue
        logging.info(f"...Find forecast for {request} in {att.filename} of type {att.content_type}")
        grib_path = ATTACHMENTS_PATH + '/' + fname
        pathlib.Path(ATTACHMENTS_PATH).mkdir(parents=True, exist_ok=True)
        with open(grib_path, 'wb') as f:
            f.write(att.part.get_payload(decode=True))
        logging.info(f"...Saved grib file into {grib_path}")
        state = forward_forecast(state, mail_conf, request, time_recvd, grib_path)
        processed = True

    if not processed:
        logging.error(f"COULD NOT FIND ANY FORECAST IN THIS MAIL:\n{msg}\n")

    return state


def answer_service(state, mail_conf, msg):
    """
    Answer the mail:
    - If that's a weather request, actually perform the request.
    - If it's a weather response, forward it to the sailor.
    For this, store a state in RAM.
    """
    logging.info(f"Answering mail which msg-id is {msg.uid}")
    is_from_garmin = (
        msg.subject.startswith('Message inReach') and
        msg.from_ == 'no.reply.inreach@garmin.com'
    )

    if is_from_garmin:
        logging.info(f"...Message from sailor!")
        state = handle_weather_request(state, mail_conf, msg)
    else:
        logging.info(f"...Message from the weather forecast service!")
        state = handle_weather_answer(state, mail_conf, msg)

    return state


def check_mail(state, mail_conf):
    """
    Check the inbox for unseen Garmin InReach messages.
    """
    had_mail = False
    with MailBox(mail_conf['imap-host']).login(mail_conf['username'], mail_conf['password'], mail_conf['folder']) as mailbox:
        for msg in mailbox.fetch(AND(seen=False)):
            had_mail = True
            print(f"New email: Subject:{msg.subject}, Date:{msg.date_str}", flush=True)
            try:
                state = answer_service(state, mail_conf, msg)
            except Exception as e:
                logging.error("CANNOT ANSWER EMAIL!")
                logging.error(traceback.format_exc())
    if not had_mail:
        logging.debug("No new mails.")

    return state


def read_state(state_file):
    if os.path.exists(state_file):
        with open(state_file, 'r') as f:
            try:
                state = json.load(f)
                logging.debug(f"Reading {len(state)} forecast requests from {state_file}")
                return state
            except json.decoder.JSONDecodeError:
                print(f"CANNOT PARSE STATE FILE {state_file}, STARTING FROM SCRATCH!", flush=True)
    return []


def save_state(state_file, state):
    logging.debug(f"Saving {len(state)} forecast requests into {state_file}")
    with open(state_file, 'w+') as f:
        json.dump(state, f, indent=2)


def timeout_state(state):
    # TODO
    return state


def main():
    parser = argparse.ArgumentParser(
        prog="mail2grib",
        description="Answer weather requests from email via Garmin InReach"
    )
    parser.add_argument('-m', '--mail-conf', default='.mail-conf.json', help="JSON file with the mail server parameters")
    parser.add_argument('-l', '--long-delay', type=int, default=60, help="How long to sleep in between two mailbox checks when no weather forecast request is going on")
    parser.add_argument('-s', '--short-delay', type=int, default=5, help="How long to sleep in between two mailbox checks when some weather forecast requests are going on")
    parser.add_argument('--state-file', help="JSON file where the internal state is saved", default=".state.json")
    parser.add_argument('-c', '--count', type=int, default=0, help="How many emails to handle before quitting (0: loop forever)")
    parser.add_argument('-d', '--debug', action='store_true', help="Verbose logs")
    parser.add_argument('--encode', help="Just encode this file and quit")
    args = parser.parse_args()

    level=logging.INFO
    if args.debug:
        level=logging.DEBUG
    logging.basicConfig(format='%(asctime)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S', level=level)

    with open(args.mail_conf, 'r') as f:
        mail_conf = json.load(f)

    random.seed()

    if args.encode:
        encode(args.encode, just_print)
        exit(0)

    num_loops = 0
    while(args.count <= 0 or num_loops < args.count):
        num_loops += 1
        state = read_state(args.state_file)
        try:
            state = check_mail(state, mail_conf)
            state = timeout_state(state)
            save_state(args.state_file, state)
        except TimeoutError:
            logging.warning("Timeout! Let's pause for a bit...\n")
            time.sleep(500)
        if len(state) > 0:
            time.sleep(args.short_delay)
        else:
            time.sleep(args.long_delay)

main()
