import json
import urllib
import urlparse

import flask

import settings


def auth_url():
    url = "https://github.com/login/oauth/authorize"
    return url + "?client_id=" + settings.gh_client_id


def token_for_code(code):
    url = "https://github.com/login/oauth/access_token"
    params = urllib.urlencode({"client_id": settings.gh_client_id,
                               "client_secret": settings.gh_secret,
                               "code": code})
    response = urlparse.parse_qs(urllib.urlopen(url, params).read())
    return response.get("access_token", [None])[0]


def make_request(u, big=False):
    u = "https://api.github.com%s?access_token=%s" % (u, flask.session["t"])
    if big:
        u += "&per_page=100"
    return json.load(urllib.urlopen(u))


def user_info():
    return make_request("/user")


def repos(org=None):
    if org:
        return make_request("/orgs/%s/repos" % org)
    return make_request("/user/repos")


def filtered(c, i):
    return [{"l": x["login"], "i": x["id"]} for x in c if x["login"] not in i]


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
