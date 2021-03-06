#!/usr/bin/env python

import json
import re
import sys
import threading
import time
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


# GH API rate is 60 calls per minute, but we run this from two
# processes, so each gets 30 per minute.
SLEEP_INTERVAL = 2.1

class SendInvites(threading.Thread):
    '''
    We send invites from a separate thread to try to avoid going over
    GH's rate limit (60 calls per minute for V2 API).
    '''

    def run(self):
        while True:
            invite = db.next_invite()
            if not invite:
                time.sleep(SLEEP_INTERVAL)
                continue

            repo_name = invite["repo_name"]
            github_url = invite["github_url"]
            inviter = invite["inviter"]
            username = invite["username"]
            group = fiesta.FiestaGroup.from_id(fiesta_api, invite["group_id"])

            welcome_message = {"subject": "Invitation to %s@gitlists.com" % repo_name,
                               "markdown": """
[%s](%s) invited you to a [Gitlist](https://gitlists.com) for [%s](%s). Gitlists are dead-simple mailing lists for GitHub projects.

[Click here]($invite_url) to join the list. If you don't want to join, just ignore this message.

Have a great day!
""" % (inviter, "http://github.com/" + inviter, repo_name, github_url)}

            user, cache = github.user_info(username)
            if user.get("email", None):
                group.add_member(user["email"],
                                 display_name=user.get("name", ""),
                                 welcome_message=welcome_message,
                                 send_invite=True)

            if not cache:
                time.sleep(SLEEP_INTERVAL)


# Invite thread
send_invites = SendInvites()
send_invites.daemon = True
send_invites.start()


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
            redirect = flask.request.headers.get("REFERER", "/")
            return flask.redirect(redirect)
        return view(*args, **kwargs)
    return decorator.decorator(check_xsrf)


@app.route("/rate_limited")
def rate_limited():
    return flask.render_template("rate_limited.html")


@app.route("/")
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


def repo_page(name, org=None):
    user = github.current_user()
    repo = repo_data(name, org and org["login"])

    if not repo:
        return flask.abort(404, "No matching repo")

    existing_own = list(db.existing_own(name, user["login"]))
    existing_not_own = list(db.existing_not_own(name, user["login"]))

    return flask.render_template("repo.html", repo=repo, org=org,
                                 existing_own=existing_own,
                                 existing_not_own=existing_not_own,
                                 **gen_xsrf(["create"]))


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


def repo_create(name, org=None):
    user = github.current_user()
    repo = repo_data(name, org and org["login"])

    if not repo:
        return flask.abort(404, "No matching repo")

    username = org and org["login"] or user["login"]

    to_invite = set()
    to_invite.update(github.collaborators(username, name))
    to_invite.update(github.contributors(username, name))
    if org:
        to_invite.update(github.members(org["login"]))
    to_invite.update(github.forkers(username, name))
    to_invite.update(github.watchers(username, name))
    to_invite -= set([user["login"], "invalid-email-address"])

    description = repo["description"]
    group = fiesta_api.create_group(default_name=repo["name"],
                                    description=description)

    # Gitlists are public, archived and have the repo name as a subject-prefix
    group.add_application("public", group_name=repo["name"])
    group.add_application("subject_prefix", prefix=repo["name"])
    group.add_application("archive")

    github_url = "https://github.com/%s/%s" % (username, repo["name"])
    welcome_message = {"subject": "Welcome to %s@gitlists.com" % repo["name"],
                       "markdown": """
Your [Gitlist](https://gitlists.com) for [%s](%s) has been created.

The [list page](https://fiesta.cc/list/%s) is the archive *and* where new members will need to go to join the list, so you might want to add it to your repo's README.

If you have any questions, send us an email at support@corp.fiesta.cc.

Have a great day!
""" % (repo["name"], github_url, group.id)}
    group.add_member(user["email"],
                     display_name=user.get("name", ""),
                     welcome_message=welcome_message)

    for username in to_invite:
        db.pending_invite(repo["name"], github_url, user["login"],
                          username, group.id)

    db.new_list(repo["name"], user["login"], group.id)
    flask.flash("Your Gitlist has been created - check your email at '%s'." % user["email"])
    return flask.redirect("/")


@app.route("/repo/<name>", methods=["POST"])
@github.rate_limit
@github.authorized
@check_xsrf("create")
def create_repo(name):
    if "g" not in flask.session:
        return flask.abort(403, "No user")
    return repo_create(name)


@app.route("/repo/<org_handle>/<name>", methods=["POST"])
@github.rate_limit
@github.authorized
@check_xsrf("create")
def create_org_repo(org_handle, name):
    if "g" not in flask.session:
        return flask.abort(403, "No user")

    for org in github.orgs():
        if org["login"] == org_handle:
            return repo_create(name, org)

    return flask.abort(404, "No matching org")


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
