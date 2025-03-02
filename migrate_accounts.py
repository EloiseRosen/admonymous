#!/usr/bin/env python3
from google.cloud import datastore

"""
migrate from legacy `google_account` to new `google_account_str`:
create a google_account_str column in the User table while keeping the old google_account column so that both
versions of the app willl continue to work until the full transition is complete.
"""

client = datastore.Client(project='crockersrules-hrd')
query = client.query(kind="User")  # only updating User table, because that's the only one that has google_account

for entity in query.fetch(): 
     #  entity["google_account"] is  {"email": "someone@gmail.com",  .... } 
    if 'google_account' in entity and entity['google_account'] is not None:
        user_prop = entity['google_account']
        
        # check if we already have `google_account_str``
        if 'google_account_str' not in entity or not entity['google_account_str']:
            email_str = None
            if isinstance(user_prop, dict) and "email" in user_prop:
                email_str = user_prop["email"]
            elif isinstance(user_prop, str):
                email_str = user_prop  # rare case: it might already be a string
            
            if email_str:
                print(f'on email: {email_str}')
                entity['google_account_str'] = email_str
                client.put(entity) # write back to database

