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


def make_request(u):
    u = "https://api.github.com%s?access_token=%s" % (u, flask.session["t"])
    return json.load(urllib.urlopen(u))


def user_info():
    return make_request("/user")


def repos(org=None):
    if org:
        return make_request("/orgs/%s/repos" % org)
    return make_request("/user/repos")


def orgs():
    return make_request("/user/orgs")


def members(org):
    return make_request("/orgs/%s/members" % org)
