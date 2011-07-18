import urlparse

from decorator import decorator
import flask

import db
import github
import errors
import json
import settings
import sign


app = flask.Flask(__name__)
app.secret_key = settings.session_key


def flash(message):
    raise errors.TODO("flash")


def _gen_xsrf(action):
    return sign.sign(action + flask.session["t"])


def gen_xsrf(actions):
    xsrf = {}
    for action in actions:
        xsrf[action] = _gen_xsrf(action)
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

        msg = action + flask.session["t"]
        status = sign.check_sig(msg, flask.request.form.get("x"), timeout)
        if status == sign.BAD:
            return flask.abort(403, "Bad XSRF token.")
        elif status == sign.TIMEOUT:
            flash("Your session timed out, please try again.")
            return flask.redirect(flask.request.headers.get("REFERER", "/"))
        return view(*args, **kwargs)
    return decorator(check_xsrf)


def user_data():
    try:
        user = db.user(flask.session["i"])
        if user:
            return user
    except:
        pass

    user = github.user_info()
    flask.session["i"] = user["id"]
    db.email(user["id"], user["email"])

    doc = {"name": user["name"],
           "email": user["email"],
           "url": user["html_url"],
           "handle": user["login"],
           "avatar": user["avatar_url"],
           "repos": [],
           "orgs": []}

    for repo in github.repos():
        if not repo["fork"]:
            doc["repos"].append({"name": repo["name"],
                                 "description": repo["description"]})
    for org in github.orgs():
        org = {"id": org["id"],
               "handle": org["login"],
               "avatar": org["avatar_url"],
               "repos": []}
        for repo in github.repos(org=org["handle"]):
            org["repos"].append({"name": repo["name"],
                                 "description": repo["description"]})
        doc["orgs"].append(org)

    db.user(user["id"], doc)
    return doc


@app.route("/")
def index():
    if "t" in flask.session:
        user = "i" in flask.session and db.user(flask.session["i"])
        if not user:
            user = user_data()
        return flask.render_template("index_logged_in.html",
                                     user=user, **gen_xsrf(["refresh"]))
    return flask.render_template("index.html")


def repo_data(user, repo, name, org=None):
    username = org and org["handle"] or user["handle"]

    ignore = set([user["handle"], "invalid-email-address"])

    def query(function):
        result = function(username, name, ignore)
        ignore.update([x["l"] for x in result])
        return result

    # Note that order of these calls matters as we are updating `ignore`.
    repo["collaborators"] = query(github.collaborators)
    repo["contributors"] = query(github.contributors)

    if org:
        org_members = github.members(org["handle"], ignore)
        repo["org_members"] = org_members

    repo["forkers"] = query(github.forkers)
    repo["watchers"] = query(github.watchers)

    db.user(user["_id"], user)


def repo_page(user, repos, name, org=None):
    repo = None
    for r in repos:
        if r["name"] == name:
            repo = r
    if not repo:
        return flaswwk.abort(404, "No matching repo")

    if "collaborators" not in repo:
        repo_data(user, repo, name, org)

    return flask.render_template("repo.html", user=user,
                                 repo=repo, org=org,
                                 **gen_xsrf(["refresh_repo", "create"]))


@app.route("/repo/<name>")
def repo(name):
    user = "i" in flask.session and db.user(flask.session["i"])
    if not user:
        return flask.abort(403, "No user")

    return repo_page(user, user["repos"], name)


@app.route("/repo/<org_handle>/<name>")
def org_repo(org_handle, name):
    user = "i" in flask.session and db.user(flask.session["i"])
    if not user:
        return flask.abort(403, "No user")

    for org in user["orgs"]:
        if org["handle"] == org_handle:
            return repo_page(user, org["repos"], name, org)

    return flask.abort(404, "No matching org")


@app.route("/refresh", methods=["POST"])
@check_xsrf("refresh")
def refresh():
    if "i" in flask.session:
        db.delete_user(flask.session["i"])
    return flask.redirect("/")


@app.route("/refresh_repo", methods=["POST"])
@check_xsrf("refresh_repo")
def refresh_repo():
    raise errors.TODO("delete repo info")


@app.route("/auth/request")
def auth_request():
    return flask.redirect(github.auth_url())


@app.route("/auth/response")
def auth_response():
    code = flask.request.args.get("code", "")
    token = github.token_for_code(code)
    if token:
        flask.session["t"] = token
    return flask.redirect("/")


if __name__ == '__main__':
    app.run(debug=True)
