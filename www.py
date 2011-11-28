#!/usr/bin/env python

import json
import re
import sys
import urlparse

import decorator
import fiesta
import flask
from paste.exceptions.errormiddleware import ErrorMiddleware

import daemon
import db
import github
import errors
import settings
import sign
import werkzeug_monkeypatch


fiesta_api = fiesta.FiestaAPI(settings.fiesta_id,
                              settings.fiesta_secret,
                              "gitlists.com")


app = flask.Flask(__name__)
app.secret_key = settings.session_key
app.config["PROPAGATE_EXCEPTIONS"] = True

if settings.env == "prod":
    app.wsgi_app = ErrorMiddleware(app.wsgi_app, debug=False,
                                   error_email=settings.noc_address,
                                   from_address="noreply@gitlists.com",
                                   error_subject_prefix="[Gitlists] Error ",
                                   smtp_server=settings.relay_host)


# If you looked through the source to find this link, then you deserve
# access to the beta :).
#
# But, if you don't mind, keep it on the DL. It's top secret.
INDEX = "/top_secret"


def gen_xsrf(actions):
    xsrf = {}
    for action in actions:
        xsrf[action] = sign.sign(action + flask.session["g"])
    return {"xsrf": xsrf}


def until(s, x):
    s, _, _ = s.partition(x)
    return s


def check_referrer():
    referrer = flask.request.headers.get("REFERER")
    if not referrer:
        return flask.abort(403, "No referrer")
    referrer = until(urlparse.urlsplit(referrer)[1], ":")
    if referrer != until(flask.request.headers.get("HOST"), ":"):
        return flask.abort(403, "Bad referrer.")
    return None


def check_xsrf(action, timeout=60*60):
    def check_xsrf(view, *args, **kwargs):
        res = check_referrer()
        if res:
            return res

        msg = action + flask.session["g"]
        status = sign.check_sig(msg, flask.request.form.get("x"), timeout)
        if status == sign.BAD:
            return flask.abort(403, "Bad XSRF token.")
        elif status == sign.TIMEOUT:
            flask.flash("Your session timed out, please try again.")
            redirect = flask.request.headers.get("REFERER", INDEX)
            return flask.redirect(redirect)
        return view(*args, **kwargs)
    return decorator.decorator(check_xsrf)


@app.route("/")
def beta_index():
    return flask.render_template("beta_index.html")


@app.route("/beta", methods=["POST"])
def beta_post():
    username = flask.request.form.get("github", "").strip()
    if not username or not re.match(r"^[a-zA-Z0-9\-]+$", username):
        flask.flash("Invalid GitHub username.")
    else:
        db.beta(username)
        flask.flash("Thanks %s, we'll let you know when the party's on!" % username)
    return flask.redirect("/")


@app.route("/rate_limited")
def rate_limited():
    return flask.render_template("rate_limited.html")


@app.route(INDEX)
@github.reauthorize
@github.rate_limit
def index():
    if "g" in flask.session:
        user = github.current_user()
        flask.session["e"] = user["email"]
        orgs = github.orgs()
        org_repos = [github.repos(org=org["login"]) for org in orgs]
        return flask.render_template("index_logged_in.html",
                                     user=user,
                                     repos=github.repos(),
                                     orgs=orgs, org_repos=org_repos)
    return flask.render_template("index.html", auth_url=github.auth_url())


def repo_data(name, org_name=None):
    for r in github.repos(org_name):
        if r["name"] == name:
            return r
    return None


@github.authorized
def repo_page(name, org=None):
    user = github.current_user()
    repo = repo_data(name, org and org["login"])

    if not repo:
        return flask.abort(404, "No matching repo")

    username = org and org["login"] or user["login"]

    ignore = set([user["login"], "invalid-email-address"])

    def query(function):
        result = function(username, name, ignore)
        ignore.update(result)
        return result

    # Note that order of these calls matters as we are updating `ignore`.
    collaborators = query(github.collaborators)
    contributors = query(github.contributors)

    org_members = []
    if org:
        org_members = github.members(org["login"], ignore)
        ignore.update(org_members)

    forkers = query(github.forkers)
    watchers = query(github.watchers)

    n = len([x for x in [collaborators, contributors,
                         org_members, forkers, watchers] if x])

    if n == 1:
        n = "1"
    elif n:
        n = "1-%s" % n

    return flask.render_template("repo.html", user=user, n=n,
                                 repo=repo, org=org,
                                 collaborators=collaborators,
                                 contributors=contributors,
                                 org_members=org_members,
                                 forkers=forkers,
                                 watchers=watchers)


@app.route("/repo/<name>")
@github.rate_limit
@github.authorized
def repo(name):
    if "g" not in flask.session:
        return flask.abort(403, "No user")
    return repo_page(name)


@app.route("/repo/<org_handle>/<name>")
@github.rate_limit
@github.authorized
def org_repo(org_handle, name):
    if "g" not in flask.session:
        return flask.abort(403, "No user")

    for org in github.orgs():
        if org["login"] == org_handle:
            return repo_page(name, org)

    return flask.abort(404, "No matching org")


def valid_email(e):
    """Just basic safety"""
    lcl, _, host = e.partition("@")
    if not lcl or not host or "@" in host or "." not in host:
        return False
    for char in "()[]\;:,<>":
        if char in e:
            return False
    return True


def repo_url(repo, org=None):
    return "/repo/%s%s" % (org and org + "/" or "", repo)


@app.route("/create", methods=["GET"])
@github.rate_limit
@github.authorized
def create_get():
    repo = flask.request.args.get("repo")
    org = flask.request.args.get("org")

    usernames = flask.request.args.getlist("username")
    addresses = flask.request.args.getlist("address")
    addresses = [a for a in addresses if valid_email(a)]

    if not addresses and not usernames:
        flask.flash("Please select some list members before creating your list.")
        return flask.redirect(repo_url(repo, org))

    return flask.render_template("create.html", user=github.current_user(),
                                 repo=repo, org=org, usernames=usernames,
                                 addresses=addresses, **gen_xsrf(["create"]))


@app.route("/create", methods=["POST"])
@github.rate_limit
@github.authorized
@check_xsrf("create")
def create_post():
    user = github.current_user()

    repo = flask.request.form.get("repo")
    org = flask.request.form.get("org")
    repo_obj = repo_data(repo, org)

    usernames = flask.request.form.getlist("username")
    addresses = flask.request.form.getlist("address")
    addresses = dict([(a, None) for a in addresses if valid_email(a)])

    if not addresses and not usernames:
        flask.flash("Please select some list members before creating your list.")
        return flask.redirect(repo_url(repo, org))

    github_url = "https://github.com/%s/%s" % (org or user["login"], repo)
    description = repo_obj["description"]
    welcome_message = {"subject": "Welcome to %s@gitlists.com" % repo,
                       "markdown": """
[%s](%s) added you to a Gitlist for [%s](%s). Gitlists are dead-simple mailing lists for GitHub projects. You can create your own at [gitlists.com](https://gitlists.com).

Use %s@gitlists.com to email the list. Use the "List members" link below to see, add or remove list members. Use the "Unsubscribe" link below if you don't want to receive any messages from this list.
""" % (user["login"], "http://github.com/" + user["login"],
       repo, github_url,
       repo)}

    group = fiesta_api.create_group(default_name=repo,
                                    description=description)
    # Gitlists are public, archived and have the repo name as a subject-prefix
    group.add_application("public", group_name=repo)
    group.add_application("subject_prefix", prefix=repo)
    group.add_application("archive")

    group.add_member(user["email"],
                     display_name=user.get("name", ""),
                     welcome_message=welcome_message)

    for address in addresses:
        group.add_member(address, welcome_message=welcome_message)

    for username in usernames:
        member_user = github.user_info(username)
        if not member_user.get("email", None):
            continue

        group.add_member(member_user["email"],
                         display_name=member_user.get("name", ""),
                         welcome_message=welcome_message)

    flask.flash("Your Gitlist has been created - you should receive a welcome email at '%s'." % user["email"])
    return flask.redirect(INDEX)


@app.route("/auth/github")
def auth_github():
    return github.finish_auth()


@app.route("/favicon.ico")
def favicon():
    return app.send_static_file("i/favicon.ico")


@app.route("/error", methods=["GET", "POST"])
def get_error():
    """
    Force an exception so we can test our error handling.
    """
    raise Exception("error")


class GitlistsDaemon(daemon.Daemon):
    def __init__(self, port, *args, **kwargs):
        self.port = port
        return daemon.Daemon.__init__(self, *args, **kwargs)

    def run(self):
        db.create_indexes()
        app.run(host=settings.host, port=self.port)


if __name__ == '__main__':
    port = 7176
    if len(sys.argv) > 2:
        port = int(sys.argv[2])
    if settings.env == "prod":
        daemon.go(GitlistsDaemon(port, "/tmp/gitlists-%s.pid" % port))
    else:
        db.create_indexes()
        app.run(host=settings.host, port=port, debug=True)
