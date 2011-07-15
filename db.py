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
        db.emails.save({"_id": user_id, "a": address})
    else:
        x = db.emails.find_one({"_id": user_id})
        return x and x["a"]
