import json
import urllib
import urlparse

import decorator
import flask

import db
import settings


urlopen = urllib.urlopen


class Error(Exception):
    pass


class Reauthorize(Error):
    pass


class RateLimited(Error):
    pass


@decorator.decorator
def rate_limit(view, *args, **kwargs):
    try:
        return view(*args, **kwargs)
    except RateLimited:
        return flask.redirect("/rate_limited")


@decorator.decorator
def reauthorize(view, *args, **kwargs):
    try:
        return view(*args, **kwargs)
    except Reauthorize:
        del flask.session["g"]
        return flask.redirect("/")


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
    response = urlparse.parse_qs(urlopen(url, params).read())
    return response.get("access_token", [None])[0]


def finish_auth():
    flask.session["g"] = token(flask.request.args["code"])
    return flask.redirect("/")


def make_request(u, big=False, memoize=False):
    # We try to memo-ize requests to keep from hammering GH's API.
    u = "https://api.github.com%s?access_token=%s" % (u, flask.session["g"])
    if big:
        u += "&per_page=100"
    if memoize:
        data = db.memoized(u)
    if not memoize or not data:
        try:
            data = urlopen(u).read()
            if memoize:
                db.memoize(u, data)
        except IOError, e:
            if e.args[1] == 401:
                raise Reauthorize("Got a 401...")
            else:
                raise
    res = json.loads(data)
    if "error" in res:
        if "Rate Limit" in res["error"]:
            raise RateLimited()
        raise Error("GitHub error: " + repr(res["error"]))
    return res


def current_user():
    data = make_request("/user")
    if data and data.get("email", None):
        db.save_user(data["login"],
                     data.get("email", None),
                     data.get("name", None))
    elif data:
        email = make_request("/user/emails")[0]
        data["email"] = email
        db.save_user(data["login"], email, data.get("name", None))
    return data


def user_info(username):
    existing = db.user(username)
    if existing:
        return existing

    u = "http://github.com/api/v2/json/user/show/" + username
    data = json.loads(urlopen(u).read())
    if "error" in data:
        if "Rate Limit" in data["error"][0]:
            raise RateLimited()
        raise Error("GitHub error: " + repr(data["error"]))
    data = data["user"]
    db.save_user(username, data.get("email", None), data.get("name", None))
    return data


def repos(org=None):
    if org:
        return make_request("/orgs/%s/repos" % org, memoize=True)
    return make_request("/user/repos")


def user_list(url):
    c = make_request(url, True, True)
    if not c or isinstance(c, dict):
        return []
    return [x["login"] for x in c]


def collaborators(user, name):
    # TODO this call doesn't seem to be working for some reason...
    return user_list("/repos/%s/%s/collaborators" % (user, name))


def contributors(user, name):
    return user_list("/repos/%s/%s/contributors" % (user, name))


def forkers(user, name):
    forks = make_request("/repos/%s/%s/forks" % (user, name), True)
    if not forks or isinstance(forks, dict):
        return []
    return [f["owner"]["login"] for f in forks]


def watchers(user, name):
    return user_list("/repos/%s/%s/watchers" % (user, name))


def orgs():
    return make_request("/user/orgs")


def members(org):
    return user_list("/orgs/%s/members" % org)
