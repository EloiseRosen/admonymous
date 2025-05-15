from google.cloud import datastore

client = datastore.Client(project='crockersrules-hrd')
query = client.query(kind="User")

dct = {}  # (year, month): count
for entity in query.fetch():
    create_date = entity['create_date']
    date_tuple = (create_date.year, create_date.month)
    if date_tuple in dct:
        dct[date_tuple] += 1
    else:
        dct[date_tuple] = 1
print(dct)
