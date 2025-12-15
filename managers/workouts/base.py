import requests

class Workout:
    link: str
    host: str

    def __init__(self, link: str, host: str):
        self.link = link
        self.host = host

    def get_data(self):
        response = requests.get(self.link)
        if response.status_code == 200:
            return response.json()
        else:
            response.raise_for_status()
