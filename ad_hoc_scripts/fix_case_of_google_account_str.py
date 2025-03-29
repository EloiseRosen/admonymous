#!/usr/bin/env python3
from google.cloud import datastore

"""
fix case mismatch between new `google_account_str` email and email derived from legacy `google_account` 
object by making email derived from `google_account` always lowercase as well.
"""

client = datastore.Client(project='crockersrules-hrd')
query = client.query(kind="User")  # only updating User table, because that's the only one that has google_account

for entity in query.fetch(): 
     #  entity["google_account"] is  {"email": "someone@gmail.com",  .... } 
    if 'google_account' in entity and entity['google_account'] is not None:
        user_prop = entity['google_account']

        if isinstance(user_prop, dict) and "email" in user_prop:
            email_str = user_prop["email"].lower()
        elif isinstance(user_prop, str):
            email_str = user_prop.lower()  # rare case: it might already be a string

        print(f'on email: {email_str}')
        entity['google_account_str'] = email_str
        client.put(entity) # write back to database

