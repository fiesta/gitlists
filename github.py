"""Interacting with the Github API."""

import urllib
import urlparse

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
    return response["access_token"]
