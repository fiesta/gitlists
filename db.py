from pymongo import Connection


db = Connection(tz_aware=True)["gitlists"]
db.gh_memo.create_index("u")


def memoized(uri):
    doc = db.gh_memo.find_one({"u": uri})
    if doc:
        return doc["d"]
    return doc


def memoize(uri, data):
    db.gh_memo.save({"u": uri, "d": data})


def pending_create(creds, github_id, usernames, addresses, repo, org):
    doc = {"_id": creds["oauth_token"],
           "secret": creds["oauth_token_secret"],
           "creator_id": github_id,
           "usernames": usernames,
           "addresses": addresses,
           "repo": repo,
           "org": org}
    db.pending.save(doc, safe=True)
