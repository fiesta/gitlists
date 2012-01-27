import json
import re
import StringIO
import sys
import unittest
import urllib
sys.path[0:0] = [""]

import fiesta
import webtest

import db
import errors
import github
import settings
import www


GITHUB = {}


# A little monkey-patching
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
    return StringIO.StringIO(response)
github.urlopen = our_urlopen


sandbox = fiesta.FiestaAPISandbox(settings.fiesta_id,
                                  settings.fiesta_secret,
                                  "gitlists.com")
www.fiesta_api = sandbox


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

        sandbox.reset()

        self.db = db.db
        for c in self.db.collection_names():
            if not c.startswith("system."):
                self.db.drop_collection(c)
        db.create_indexes()

        self.app = webtest.TestApp(www.app)

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

        self.assertIn("My test repo", res)
        res = self.get("/repo/test", res)
        res = self.submit(res.form)
        self.assertIn("Gitlist has been created", res)

        mailbox = sandbox.mailbox()
        self.assertEqual(2, len(mailbox))
        self.assertEqual(1, len(mailbox["test@example.com"]))
        self.assertEqual(1, len(mailbox["mike@example.com"]))

    def test_create_own_existing(self):
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

        self.assertIn("My test repo", res)
        res = self.get("/repo/test", res)
        res = self.submit(res.form)
        self.assertIn("Gitlist has been created", res)

        mailbox = sandbox.mailbox()
        self.assertEqual(2, len(mailbox))
        self.assertEqual(1, len(mailbox["test@example.com"]))
        self.assertEqual(1, len(mailbox["mike@example.com"]))

        res = self.get("/repo/test", res)
        self.assertIn("You already created a gitlist(s) called <strong>test", res)

    def test_create_other_existing(self):
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

        self.assertIn("My test repo", res)
        res = self.get("/repo/test", res)
        res = self.submit(res.form)
        self.assertIn("Gitlist has been created", res)

        mailbox = sandbox.mailbox()
        self.assertEqual(2, len(mailbox))
        self.assertEqual(1, len(mailbox["test@example.com"]))
        self.assertEqual(1, len(mailbox["mike@example.com"]))

        GITHUB["/user"] = {"name": "Jim Dirolf",
                           "login": "jdirolf",
                           "email": "jim@example.com"}
        res = self.follow(self.get("/auth/github?code=dummy"))
        res = self.get("/repo/test", res)
        self.assertIn("There are already gitlist(s) called <strong>test", res)

    def test_github_rate_limiting(self):
        raise errors.TODO()
