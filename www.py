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


@app.route("/")
def index():
    if "t" in flask.session:
        user = "i" in flask.session and db.user(flask.session["i"])
        return flask.render_template("index_logged_in.html",
                                     user=user, **gen_xsrf(["refresh"]))
    return flask.render_template("index.html")


def repo_page(user, repos, name, org=None):
    repo = None
    for r in repos:
        if r["name"] == name:
            repo = r
    if not repo:
        return flask.abort(404, "No matching repo")

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


def repo_data(name, org=None):
    try:
        user = db.user(flask.session["i"])
    except:
        pass

    if not user:
        return flask.abort(403, "no user")

    if org:
        repo = user["orgs"]


@app.route("/repo_data/<name>")
def repo_data(name):
    return repo_data(name)


@app.route("/repo_data/<org_handle>/<name>")
def org_repo_data(org_handle, name):
    return repo_data(name, org_handle)


@app.route("/user_data")
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
               "repos": [],
               "members": github.members(org=org["login"])}
        for repo in github.repos(org=org["handle"]):
            org["repos"].append({"name": repo["name"],
                                 "description": repo["description"]})
        doc["orgs"].append(org)

    db.user(user["id"], doc)
    return json.dumps(doc)


@app.route("/refresh", methods=["POST"])
@check_xsrf("refresh")
def refresh():
    if "i" in flask.session:
        db.delete_user(flask.session["i"])
    return flask.redirect("/")


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
