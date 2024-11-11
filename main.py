import os
import json
import logging

from google.oauth2 import service_account
from googleapiclient.discovery import build
import yaml
import requests
from datetime import datetime, timedelta
from datetime import date as date_class
import pytz

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

SCOPES = ['https://www.googleapis.com/auth/calendar']
CONFERENCES = ("coling", "neurips [dataset and benchmarks track]", "aaai", "emnlp", "neurips", "acl", "uai", "colm",
               "eccv", "naacl", "cscw", "aistats", "wacv", "icassp", "3dv", "chi", "iclr", "iccv", "eacl",
               "interspeech", "wacv", "bmvc", "facct", "cvpr", "icml")
CALENDAR_ID = "stai.there@gmail.com"
SOURCE_YAML_URL = 'https://raw.githubusercontent.com/paperswithcode/ai-deadlines/refs/heads/gh-pages/_data/conferences.yml'
CUTOFF_YEAR = 2024


def get_calendar_service():
    credentials_json = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
    if not credentials_json:
        logging.error("Google application credentials not found in environment variables.")
        return None
    credentials_info = json.loads(credentials_json)
    credentials = service_account.Credentials.from_service_account_info(
        credentials_info, scopes=['https://www.googleapis.com/auth/calendar'])
    return build('calendar', 'v3', credentials=credentials)


def parse_date(date_str, timezone_str):
    date = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
    timezone = pytz.timezone(timezone_str.replace('UTC', 'Etc/GMT'))
    return timezone.localize(date).astimezone(pytz.UTC)


def normalize_date(date):
    if isinstance(date, str):
        return datetime.strptime(date, '%Y-%m-%d').date()
    if isinstance(date, date_class):
        return date
    raise TypeError(f"Invalid date type: {type(date)}")


def event_exists(service, calendar_id, event):
    # Extract the start and end times from the event dictionary
    if 'dateTime' in event['start']:
        start_time = datetime.fromisoformat(event['start']['dateTime'].replace('Z', '+00:00'))
        end_time = datetime.fromisoformat(event['end']['dateTime'].replace('Z', '+00:00'))
    else:
        start_time = datetime.fromisoformat(event['start']['date'])
        end_time = datetime.fromisoformat(event['end']['date'])

    # Ensure times are in UTC
    start_time = start_time.astimezone(pytz.UTC)
    end_time = end_time.astimezone(pytz.UTC)

    # Format times for the API request
    time_min = start_time.isoformat()
    time_max = end_time.isoformat()

    try:
        events_result = service.events().list(calendarId=calendar_id,
                                              timeMin=time_min,
                                              timeMax=time_max,
                                              q=event['summary'],
                                              singleEvents=True,
                                              orderBy='startTime').execute()
        events = events_result.get('items', [])
        return len(events) > 0
    except Exception as e:
        logging.error(f"Error checking for event existence: {e}")
        return False


def create_event(service, conference):
    deadline = parse_date(conference['deadline'], conference['timezone'])
    start_date = normalize_date(conference['start'])
    end_date = normalize_date(conference['end'])

    # Include location in the description
    description = ""
    if "full_name" in conference:
        description += f"{conference['full_name']}\n"
    if "place" in conference:
        description += f"Location: {conference['place']}\n"
    if "link" in conference:
        description += f"Website: {conference['link']}"

    deadline_event = {
        'summary': f"{conference['title']} Deadline",
        'description': description,
        'location': conference['place'],
        'start': {'dateTime': deadline.isoformat()},
        'end': {'dateTime': (deadline + timedelta(minutes=1)).isoformat()},
        'transparency': 'transparent'
    }

    conference_event = {
        'summary': conference['title'],
        'description': description,
        'location': conference['place'],
        'start': {'date': start_date.isoformat()},
        'end': {'date': end_date.isoformat()},
        'transparency': 'transparent'
    }

    if event_exists(event=deadline_event, service=service, calendar_id=CALENDAR_ID):
        logging.info(f"Event {conference['title']} Deadline already exists")
    else:
        service.events().insert(calendarId=CALENDAR_ID, body=deadline_event).execute()
        logging.info(f"Created event: {conference['title']} Deadline")

    if event_exists(event=conference_event, service=service, calendar_id=CALENDAR_ID):
        logging.info(f"Event {conference['title']} already exists")
    else:
        service.events().insert(calendarId=CALENDAR_ID, body=conference_event).execute()
        logging.info(f"Created event: {conference['title']}")

def main():
    service = get_calendar_service()
    response = requests.get(SOURCE_YAML_URL)
    logging.info(f"Response status code: {response.status_code}")
    
    if response.status_code != 200:
        logging.error(f"Failed to fetch conferences: {response.text}")
        return
    
    conferences = yaml.safe_load(response.text)
    for conference in conferences:
        if conference['title'].lower() not in CONFERENCES:
            continue
        if conference['year'] < CUTOFF_YEAR:
            continue
        logging.info(f"Adding {conference['id']}...")
        create_event(service, conference)


if __name__ == '__main__':
    main()
