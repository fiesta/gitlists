import base64
import json
import urllib
import urllib2
import urlparse

import decorator
import flask

import settings


class Reauthorize(Exception):
    pass


@decorator.decorator
def authorized(view, *args, **kwargs):
    if "f" not in flask.session:
        return flask.redirect(auth_url(flask.request.url))
    try:
        return view(*args, **kwargs)
    except Reauthorize:
        del flask.session["f"]
        return flask.redirect(auth_url(flask.request.url))


def auth_url(next):
    return "https://fiesta.cc/authorize?response_type=code&scope=create%%20modify&client_id=%s&state=%s" % \
        (settings.fiesta_id, urllib.quote(next))


def auth_request(url):
    userpass = settings.fiesta_id + ":" + settings.fiesta_secret
    auth = "Basic " + base64.b64encode(userpass)
    req = urllib2.Request(url)
    req.add_header("Authorization", auth)
    return req


def token(code):
    req = auth_request("https://api.fiesta.cc/token")
    data = urllib.urlencode({"grant_type": "authorization_code", "code": code})
    return json.load(urllib2.urlopen(req, data))["access_token"]


def request(url, data=None, json=False):
    req = urllib2.Request("https://api.fiesta.cc/" + url)
    req.add_header("Authorization", "Bearer " + flask.session["f"])
    if json:
        req.add_header("Content-Type", "application/json")
    try:
        return urllib2.urlopen(req, data).read()
    except urllib2.HTTPError, e:
        if e.code == 401:
            raise Reauthorize("Got a 401...")
        else:
            raise


def json_request(url, data=None):
    if data:
        data = json.dumps(data)
    return json.loads(request(url, data, json=True))
