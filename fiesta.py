import base64
import json
import time
import urllib
import urllib2
import urlparse

import decorator
import flask

import settings


INDEX = "/top_secret"


@decorator.decorator
def authorize(view, *args, **kwargs):
    if "f" not in flask.session or \
            "t" not in flask.session or \
            time.time() - flask.session["t"] > 30*60:
        if flask.request.method == "GET":
            return flask.redirect(auth_url(flask.request.url))
        elif flask.request.method == "POST":
            referrer = flask.request.headers.get("REFERER", INDEX)
            return flask.redirect(auth_url(referrer))

    return view(*args, **kwargs)


def auth_url(next):
    return "https://fiesta.cc/authorize?response_type=code&scope=create modify&client_id=%s&state=%s" % \
        (settings.fiesta_id, urllib.quote(next))


def auth_request(url):
    userpass = settings.fiesta_id + ":" + settings.fiesta_secret
    auth = "Basic " + base64.b64encode(userpass)
    req = urllib2.Request(url)
    req.add_header("Authorization", auth)
    return req


def token(code):
    grant_type = "authorization_code"
    code_name = "code"

    req = auth_request("https://api.fiesta.cc/token")
    data = urllib.urlencode({"grant_type": grant_type, "code": code})
    return json.load(urllib2.urlopen(req, data))


def finish_auth():
    token_response = token(flask.request.args["code"])
    flask.session["f"] = token_response["access_token"]
    flask.session["t"] = time.time()
    return flask.redirect(flask.request.args["state"])


def request(url, data=None, json=False):
    req = urllib2.Request("https://api.fiesta.cc/" + url)
    req.add_header("Authorization", "Bearer " + flask.session["f"])
    if json:
        req.add_header("Content-Type", "application/json")
    return urllib2.urlopen(req, data).read()


def json_request(url, data=None):
    if data:
        data = json.dumps(data)
    return json.loads(request(url, data, json=True))
