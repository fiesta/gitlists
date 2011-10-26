import json
import re
import StringIO
import sys
import unittest
import urllib
sys.path[0:0] = [""]

import webtest

import db
import www


GITHUB = {}


def monkey_patch_urllib():
    def our_urlopen(url, params=None):
        response = ""
        match = re.match(r"^https://api\.github\.com(/.*)\?.+$", url)
        if url.startswith("https://github.com/login/oauth/access_token"):
            response = '{"access_token": ["dummy"]}'
        elif match:
            response = json.dumps(GITHUB.get(match.group(1)))
        return StringIO.StringIO(response)
    urllib.urlopen = our_urlopen


class BaseTest(unittest.TestCase):

    def assertIn(self, a, b):
        # This is new in Python 2.7 - add it here for 2.6
        self.assert_(a in b, "%r not in %r" % (a, b))

    def assertNotIn(self, a, b):
        # This is new in Python 2.7 - add it here for 2.6
        self.assert_(a not in b, "%r in %r" % (a, b))

    def assertStartsWith(self, a, b):
        self.assert_(a.startswith(b), "%r doesn't start with %r" % (a, b))

    def assertEndsWith(self, a, b):
        self.assert_(a.endswith(b), "%r doesn't end with %r" % (a, b))

    def follow(self, response):
        self.assert_(response.status_int >= 300 and \
                         response.status_int < 400, response)
        location = response.location
        return self.app.get(location)

class TestWWW(BaseTest):

    def setUp(self):
        global GITHUB
        GITHUB = {}

        monkey_patch_urllib()

        self.db = db.db
        for c in self.db.collection_names():
            if not c.startswith("system."):
                self.db.drop_collection(c)
        db.create_indexes()

        self.app = webtest.TestApp(www.app)

    def test_beta_signup(self):
        res = self.app.get("/", status=200)
        self.assertIn("Apologies for being coy", res)

        res.form["github"] = "foo bar"
        res = self.follow(res.form.submit())
        self.assertIn("Invalid github username", res)

        res.form["github"] = "mdirolf"
        res = self.follow(res.form.submit())
        self.assertIn("Thanks mdirolf", res)

        res.form["github"] = "mdirolf"
        res = self.follow(res.form.submit())
        self.assertIn("Thanks mdirolf", res)

    def test_github_auth_without_email(self):
        global GITHUB
        GITHUB = {"/user": {"name": "Mike Dirolf", "login": "mdirolf"},
                  "/user/emails": ["mike@example.com"],
                  "/user/orgs": [],
                  "/user/repos": []}

        # Just make sure we don't get an exception here...
        self.follow(self.app.get("/auth/github?code=dummy"))
