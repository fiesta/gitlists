from pymongo import Connection


db = Connection(tz_aware=True)["gitlists"]


def user(user_id, doc=None):
    if doc:
        doc["_id"] = user_id
        db.users.save(doc, safe=True)
    else:
        return db.users.find_one({"_id": user_id})


def delete_user(user_id):
    db.users.remove({"_id": user_id})


def email(user_id, address=None):
    if address:
        db.emails.save({"_id": user_id, "a": address}, safe=True)
    else:
        x = db.emails.find_one({"_id": user_id})
        return x and x["a"]


def pending_create(creds, github_id, usernames, addresses, repo, org):
    doc = {"_id": creds["oauth_token"],
           "secret": creds["oauth_token_secret"],
           "creator_id": github_id,
           "usernames": usernames,
           "addresses": addresses,
           "repo": repo,
           "org": org}
    db.pending.save(doc, safe=True)


def get_pending(token_id):
    return db.pending.find_one({"_id": token_id})


def delete_pending(token_id):
    return db.pending.remove({"_id": token_id}, safe=True)


def add_fiesta_token(user_id, token):
    db.users.update({"_id": user_id}, {"$set": token}, safe=True)
