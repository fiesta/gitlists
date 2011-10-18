import json
import urllib
import urlparse

import decorator
import flask

import db
import settings


INDEX = "/top_secret"


class Reauthorize(Exception):
    pass


@decorator.decorator
def reauthorize(view, *args, **kwargs):
    try:
        return view(*args, **kwargs)
    except Reauthorize:
        del flask.session["g"]
        return flask.redirect(INDEX)


@decorator.decorator
def authorized(view, *args, **kwargs):
    if "g" not in flask.session:
        return flask.redirect(auth_url())
    try:
        return view(*args, **kwargs)
    except Reauthorize:
        return flask.redirect(auth_url())


def auth_url():
    params = {"client_id": settings.gh_id,
              "scope": "user"}
    qs = urllib.urlencode(params)
    return "https://github.com/login/oauth/authorize?" + qs



def token(code):
    url = "https://github.com/login/oauth/access_token"
    params = urllib.urlencode({"client_id": settings.gh_id,
                               "client_secret": settings.gh_secret,
                               "scope": "user",
                               "code": code})
    response = urlparse.parse_qs(urllib.urlopen(url, params).read())
    return response.get("access_token", [None])[0]


def finish_auth():
    flask.session["g"] = token(flask.request.args["code"])
    return flask.redirect(INDEX)


def make_request(u, big=False):
    # We memo-ize requests to keep from hammering GH's API.
    u = "https://api.github.com%s?access_token=%s" % (u, flask.session["g"])
    if big:
        u += "&per_page=100"
    data = db.memoized(u)
    if not data:
        try:
            data = urllib.urlopen(u).read()
            db.memoize(u, data)
        except IOError, e:
            if e.args[1] == 401:
                raise Reauthorize("Got a 401...")
            else:
                raise
    return json.loads(data)


def current_user():
    data = make_request("/user")
    if data and data["email"]:
        db.save_user(data["login"], data["email"], data["name"])
    elif data:
        email = make_request("/user/emails")[0]
        db.save_user(data["login"], email, data["name"])
    return data


def user_info(username):
    existing = db.user(username)
    if existing:
        return existing

    u = "http://github.com/api/v2/json/user/show/" + username
    data = json.loads(urllib.urlopen(u).read())["user"]
    if data["email"]:
        db.save_user(username, data["email"], data["name"])
        return data
    return None


def repos(org=None):
    if org:
        return make_request("/orgs/%s/repos" % org)
    return make_request("/user/repos")


def filtered(c, i):
    return [x["login"] for x in c if x["login"] not in i]


def user_list(url, ignore):
    c = make_request(url, True)
    if not c or isinstance(c, dict):
        return []
    return filtered(c, ignore)


def collaborators(user, name, ignore):
    # TODO this call doesn't seem to be working for some reason...
    return user_list("/repos/%s/%s/collaborators" % (user, name), ignore)


def contributors(user, name, ignore):
    return user_list("/repos/%s/%s/contributors" % (user, name), ignore)


def forkers(user, name, ignore):
    forks = make_request("/repos/%s/%s/forks" % (user, name), True)
    if not forks or isinstance(forks, dict):
        return []
    return filtered([f["owner"] for f in forks], ignore)


def watchers(user, name, ignore):
    return user_list("/repos/%s/%s/watchers" % (user, name), ignore)


def orgs():
    return make_request("/user/orgs")


def members(org, ignore):
    return filtered(make_request("/orgs/%s/members" % org, True), ignore)
