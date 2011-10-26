import json
import re
import StringIO
import sys
import unittest
import urllib
import urllib2
sys.path[0:0] = [""]

import webtest

import db
import www


GITHUB = {}


def monkey_patch_urllib():
    def our_urlopen(url, params=None):
        response = ""
        gh_match = re.match(r"^https://api\.github\.com(/.*)\?.+$", url)
        if url.startswith("https://github.com/login/oauth/access_token"):
            response = 'access_token=dummy'
        elif url.startswith("http://github.com/api/v2/json/user/show/"):
            _, _, handle = url.rpartition("/")
            response = json.dumps(GITHUB.get("_user/" + handle))
        elif gh_match:
            response = json.dumps(GITHUB.get(gh_match.group(1)))
        elif url.startswith("https://api.fiesta.cc/token"):
            response = '{"access_token": "dummy"}'
        # TODO better mocking here :)
        elif url.startswith("https://api.fiesta.cc/group"):
            response = '{"status": {"code": 202}, "data": {"group_id": "dummy"}}'
        # TODO and here :)
        elif url.startswith("https://api.fiesta.cc/membership"):
            response = '{"status": {"code": 202}, "data": {"group_id": "dummy"}}'
        return StringIO.StringIO(response)

    def our_urlopen2(request, data):
        return our_urlopen(request.get_full_url(), data)

    urllib.urlopen = our_urlopen
    urllib2.urlopen = our_urlopen2


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

    def get(self, url, prev=None, status=None, **kwargs):
        if prev:
            cookie = prev.headers["Set-Cookie"]
            if cookie:
                kwargs["Cookie"] = cookie
        return self.app.get(url, status=status, headers=kwargs)

    def follow(self, response):
        self.assert_(response.status_int >= 300 and \
                         response.status_int < 400, response)
        location = response.location
        return self.get(location, response)

    def submit(self, form):
        headers={"REFERER": form.response.request.url}
        return self.follow(form.submit(headers=headers))


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
        res = self.get("/", status=200)
        self.assertIn("Apologies for being coy", res)

        res.form["github"] = "foo bar"
        res = self.submit(res.form)
        self.assertIn("Invalid github username", res)

        res.form["github"] = "mdirolf"
        res = self.submit(res.form)
        self.assertIn("Thanks mdirolf", res)

        res.form["github"] = "mdirolf"
        res = self.submit(res.form)
        self.assertIn("Thanks mdirolf", res)

    def test_github_auth_without_email(self):
        global GITHUB
        GITHUB = {"/user": {"name": "Mike Dirolf", "login": "mdirolf"},
                  "/user/emails": ["mike@example.com"],
                  "/user/orgs": [],
                  "/user/repos": []}

        # Just make sure we don't get an exception here...
        self.follow(self.get("/auth/github?code=dummy"))

    def test_add_user_without_name(self):
        global GITHUB
        GITHUB = {"/user": {"name": "Mike Dirolf",
                            "login": "mdirolf",
                            "email": "mike@example.com"},
                  "/user/orgs": [],
                  "/user/repos": [{"name": "test",
                                   "description": "My test repo"}],
                  "/repos/mdirolf/test/collaborators": [{"login": "testuser"}],
                  "/repos/mdirolf/test/contributors": [],
                  "/repos/mdirolf/test/forks": [],
                  "/repos/mdirolf/test/watchers": [],
                  "_user/testuser": {"user": {"email": "test@example.com"}}}

        res = self.follow(self.get("/auth/github?code=dummy"))
        res = self.follow(self.get("/auth/fiesta?code=dummy", res))

        self.assertIn("My test repo", res)
        res = self.get("/repo/test", res)
        res = res.form.submit()
        res = self.submit(res.form)
        self.assertIn("confirm your gitlist", res)
