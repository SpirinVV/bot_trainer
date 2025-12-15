import requests
import json

from garminconnect import Garmin
from garminconnect import GarminConnectConnectionError, GarminConnectAuthenticationError

class GarminWorkout(Garmin):
    def __init__(self, email: str, password: str):
        self.client: Garmin = Garmin(email, password)
        self.client.login()

    def get_workout_by_link(self, link: str) -> dict:
        workout_id = link.rstrip('/').split('/')[-1]
        data = self.get_workout_by_id(workout_id)
        return data

    def get_workout_by_id(self, workout_id: str) -> dict:
        return self.client.get_activity(workout_id)
