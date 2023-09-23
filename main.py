import yaml
import os
import time
import datetime
from loguru import logger
from requests import Session, Response
from requests.exceptions import JSONDecodeError
from dotenv import load_dotenv
from pprint import pprint

load_dotenv()

ADDRESS = os.getenv('ONCALL_ADDRESS')
USERNAME = os.getenv('ONCALL_USERNAME')
PASSWORD = os.getenv('ONCALL_PASSWORD')


class OncallAPI:

    def __init__(self):
        self.session = Session()
        self.login()

    def _add_payload(self, **kwargs) -> dict:
        payload = {}
        for key, value in kwargs.items():
            if value:
                payload[key] = value
        return payload

    @staticmethod
    def _show_response(response):
        try:
            res = response.json()
        except JSONDecodeError:
            res = response.reason
        url = response.request.path_url
        if response.status_code in [200, 201, 204]:
            logger.success(f'{url} | {res}')
        else:
            logger.error(f'{url} | {response.status_code} | {res}')

    def _request(self, method, url, json_data=None, data=None):
        response = self.session.request(method, ADDRESS + url, json=json_data, data=data)
        self._show_response(response)
        return response

    def login(self) -> None:
        response = self._request('POST', '/login', data={'username': USERNAME, 'password': PASSWORD})
        if response.status_code == 200:
            logger.success('Successfully logged in')
            csrf_token = response.json()['csrf_token']
            self.session.cookies.update(response.cookies)
            self.session.headers.update({'X-CSRF-TOKEN': csrf_token})
        else:
            logger.error(response.json())

    def create_team(self, name, scheduling_timezone, email=None, slack_channel=None, iris_plan=None):
        url = '/api/v0/teams'
        payload = {
            "name": name,
            "scheduling_timezone": scheduling_timezone,
        }
        payload = {**self._add_payload(slack_channel=slack_channel, email=email, iris_plan=iris_plan), **payload}
        response = self._request('POST', url, json_data=payload)
        return response.reason

    def add_user_to_a_team(self, team: str, user: str):
        url = f'/api/v0/teams/{team}/users'
        payload = {'name': user}
        response = self._request('POST', url, json_data=payload)
        return response.json()

    def get_all_users(self):
        url = '/api/v0/users'
        response = self._request('GET', url)
        return response.json()

    def get_user_info(self, user: str):
        url = f'/api/v0/users/{user}'
        response = self._request('GET', url)
        return response.reason

    def create_user(self, name: str):
        url = f'/api/v0/users'
        response = self._request('POST', url, json_data={'name': name})
        return response.reason

    def update_user_info(self, name: str,
                         contacts: dict = None,
                         new_name: str = None,
                         full_name: str = None,
                         time_zone: str = None,
                         photo_url: str = None,
                         active: int = None):
        url = f'/api/v0/users/{name}'
        contacts = {
            'call': contacts['phone_number'],
            'email': contacts['email']
        }
        payload = self._add_payload(
            contacts=contacts,
            new_name=new_name,
            full_name=full_name,
            time_zone=time_zone,
            photo_url=photo_url,
            active=active
        )
        response = self._request('PUT', url, json_data=payload)
        return response.reason

    def create_event(self, start: int, end: int, user: str, team: str, role: str):
        url = '/api/v0/events'
        payload = {
            'start': start,
            'end': end,
            'user': user,
            'team': team,
            'role': role
        }
        response = self._request('POST', url, json_data=payload)
        return response.reason


if __name__ == '__main__':
    with open('schedule.yaml') as f:
        schedule = yaml.safe_load(f)

    pprint(schedule)
    oncall_schedule = OncallAPI()
    for team in schedule['teams']:
        oncall_schedule.create_team(
            name=team['name'],
            scheduling_timezone=team['scheduling_timezone'],
            email=team['email'],
            slack_channel=team['slack_channel'],
            iris_plan=team['iris_plan'] if 'iris_plan' in team else None
        )
        for user in team['users']:
            oncall_schedule.create_user(user['name'])
            oncall_schedule.update_user_info(
                name=user['name'],
                contacts={'phone_number': user['phone_number'], 'email': user['email']},
                full_name=user['full_name']
            )
            oncall_schedule.add_user_to_a_team(team['name'], user['name'])
            seconds_in_day = 86400
            t_role = user['duty'][0]['role']
            date = user['duty'][0]['date']
            start = int(datetime.datetime.strptime(date, "%d/%m/%Y").timestamp())
            end = start
            for duty in user['duty']:
                date = duty['date']
                role = duty['role']
                if role != t_role:
                    oncall_schedule.create_event(
                        start=start,
                        end=end,
                        user=user['name'],
                        team=team['name'],
                        role=t_role
                    )
                    t_role = role
                    start = int(datetime.datetime.strptime(date, "%d/%m/%Y").timestamp())
                    end = start
                end += seconds_in_day
            oncall_schedule.create_event(
                start=start,
                end=end,
                user=user['name'],
                team=team['name'],
                role=t_role
            )
