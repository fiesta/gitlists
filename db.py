from pymongo import Connection
import pymongo.errors

import settings


try:
    db = Connection(replicaset="fiesta", tz_aware=True)[settings.db]
except:
    db = Connection(replicaset="fiesta", tz_aware=True)["gitlists"]


def create_indexes():
    db.memo.create_index("u")
    db.lists.create_index([("name", 1), ("username", 1)])


# Caching arbitrary URIs
def memoized(uri):
    doc = db.memo.find_one({"u": uri})
    if doc:
        return doc["d"]
    return doc


def memoize(uri, data):
    db.memo.save({"u": uri, "d": data})


# Created lists
def new_list(name, username, group_id):
    db.lists.save({"name": name,
                   "group_id": group_id,
                   "username": username}, safe=True)


def existing_own(name, username):
    return db.lists.find({"name": name, "username": username})


def existing_not_own(name, username):
    return db.lists.find({"name": name, "username": {"$ne": username}})


# Memoizing github user data
def save_user(username, email_address, display_name):
    db.users.save({"_id": username,
                   "email": email_address,
                   "name": display_name}, safe=True)


def user(username):
    return db.users.find_one({"_id": username})


# Invite queue
def pending_invite(repo_name, github_url, inviter, username, group_id):
    db.invites.save({"repo_name": repo_name,
                     "github_url": github_url,
                     "inviter": inviter,
                     "username": username,
                     "group_id": group_id}, safe=True)


def next_invite():
    return db.invites.find_and_modify(remove=True, sort={'_id': -1})
