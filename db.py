from pymongo import Connection


db = Connection(replicaset="fiesta", tz_aware=True)["gitlists"]
db.memo.create_index("u")


# Caching arbitrary URIs
def memoized(uri):
    doc = db.memo.find_one({"u": uri})
    if doc:
        return doc["d"]
    return doc


def memoize(uri, data):
    db.memo.save({"u": uri, "d": data})


# Beta signups
def beta(username):
    db.beta.save({"gh": username}, safe=True)


# Memoizing github user data
def save_user(username, email_address, display_name):
    db.users.save({"_id": username,
                   "email": email_address,
                   "name": display_name}, safe=True)


def user(username):
    return db.users.find_one({"_id": username})
