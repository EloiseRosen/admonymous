from google.cloud import ndb
import os


client = ndb.Client(
    project=os.environ.get('GCP_PROJECT_ID', 'crockersrules-hrd'),
)


class NDBMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        with client.context():
            response = self.get_response(request)
        return response