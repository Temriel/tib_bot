import json
import urllib.request
from dotenv import load_dotenv
import os


load_dotenv()


class WebHandler:
    """Class. Fetches stats from /stats/"""
    def __init__(self):
        self.request_url: str
        self.request_name: str
        self.request_token: str

        request_url = os.getenv("REQUEST_URL")
        request_name = os.getenv("REQUEST_NAME")
        request_token = os.getenv("REQUEST_TOKEN")

        if not request_url:
            raise ValueError("REQUEST_URL not set!")
        if not request_name:
            raise ValueError("REQUEST_NAME not set!")
        if not request_token:
            raise ValueError("REQUEST_TOKEN not set!")

        self.request_url = request_url
        self.request_name = request_name
        self.request_token = request_token

    def fetch_json(self):
        """Fetch json data."""
        headers = {self.request_name: self.request_token}
        req = urllib.request.Request(self.request_url, headers=headers)
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())