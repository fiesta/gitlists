import json
import urllib
import urllib2

import settings


def _auth(callback=None, token=None, verifier=None):
    token_secret = token and token["oauth_token_secret"] or ""
    signature = "%s&%s" % (settings.fiesta_secret, token_secret)
    params = {"oauth_consumer_key": settings.fiesta_client_id,
              "oauth_signature_method": "PLAINTEXT",
              "oauth_signature": signature,
              "oauth_version": "1.0"}
    if callback:
        params["oauth_callback"] = callback
    if token:
        params["oauth_token"] = token["oauth_token"]
    if verifier:
        params["oauth_verifier"] = verifier

    authorization = 'OAuth realm="https://api.fiesta.cc/", '
    p = lambda k, v: '%s="%s"' % (k, urllib.quote(str(v)))
    return authorization + ", ".join([p(k,v) for k,v in params.iteritems()])


def request(url, data=None, callback=None, token=None, verifier=None):
    auth_header = _auth(callback, token, verifier)
    req = urllib2.Request("https://api.fiesta.cc/" + url)
    req.add_header("Authorization", auth_header)
    return urllib2.urlopen(req, data).read()


def json_request(url, data=None, *args, **kwargs):
    if data:
        data = json.dumps(data)
    return json.loads(request(url, data, *args, **kwargs))


def address(email):
    try:
        return json_request("address/" + email)
    except urllib2.HTTPError, e:
        if e.code == 404:
            return None
        raise
