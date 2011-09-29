import base64
import json
import urllib
import urllib2
import urlparse

import decorator

import settings


class Reauthorize(Exception):
    pass


CLIENT_TOKEN = None


def auth_url():
    return "https://fiesta.cc/authorize?client_id=" + settings.fiesta_id


def auth_request(url):
    userpass = settings.fiesta_id + ":" + settings.fiesta_secret
    auth = "Basic " + base64.b64encode(userpass)
    req = urllib2.Request(url)
    req.add_header("Authorization", auth)
    return req


def get_client_token():
    global CLIENT_TOKEN
    req = auth_request("https://api.fiesta.cc/token")
    data = {"grant_type": "client_credentials"}
    res = urllib2.urlopen(req, urllib.urlencode(data))
    CLIENT_TOKEN = json.load(res)["access_token"]


def get_user_token(code):
    req = auth_request("https://api.fiesta.cc/token")
    data = {"grant_type": "authorization_code", "code": code}
    return json.load(urllib2.urlopen(req, data))["access_token"]


@decorator.decorator
def with_client_token(method, *args, **kwargs):
    if not CLIENT_TOKEN:
        get_client_token()
    try:
        return method(*args, **kwargs)
    except Reauthorize:
        get_client_token()
        return method(*args, **kwargs)


def request(url, data=None, callback=None, token=None, verifier=None):
    req = urllib2.Request("https://api.fiesta.cc/" + url)
    req.add_header("Authorization", "Bearer " + CLIENT_TOKEN)
    return urllib2.urlopen(req, data).read()


def auth_url():
    url = "https://github.com/login/oauth/authorize"
    return url + "?client_id=" + settings.gh_client_id


def token(code):
    url = "https://github.com/login/oauth/access_token"
    params = urllib.urlencode({"client_id": settings.gh_client_id,
                               "client_secret": settings.gh_secret,
                               "code": code})
    response = urlparse.parse_qs(urllib.urlopen(url, params).read())
    return response.get("access_token", [None])[0]


def json_request(url, data=None, *args, **kwargs):
    if data:
        data = json.dumps(data)
    return json.loads(request(url, data, *args, **kwargs))


def token(temp_creds, verifier):
    return dict(urlparse.parse_qsl(request("oauth/token",
                                           token=temp_creds,
                                           verifier=verifier)))


@with_client_token
def address(email):
    try:
        return json_request("address/" + email)
    except urllib2.HTTPError, e:
        if e.code == 404:
            return None
        elif e.code == 401:
            raise Reauthorize()
        raise
