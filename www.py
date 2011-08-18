import urlparse

from decorator import decorator
import flask

import db
import github
import errors
import fiesta
import json
import settings
import sign


app = flask.Flask(__name__)
app.secret_key = settings.session_key


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
            flask.flash("Your session timed out, please try again.")
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
            try:
                user = user_data()
            except github.Reauthorize:
                del flask.session["t"]
                del flask.session["i"]
                return flask.redirect("/")
        return flask.render_template("index_logged_in.html",
                                     user=user, **gen_xsrf(["refresh", "logout"]))
    return flask.render_template("index.html",
                                 github_auth_url=github.auth_url())


def repo_data(user, repo, name, org=None):
    username = org and org["handle"] or user["handle"]

    ignore = set([user["handle"], "invalid-email-address"])

    def query(function):
        result = function(username, name, ignore)
        ignore.update(result)
        return result

    # Note that order of these calls matters as we are updating `ignore`.
    repo["collaborators"] = query(github.collaborators)
    repo["contributors"] = query(github.contributors)

    if org:
        org_members = github.members(org["handle"], ignore)
        ignore.update([x["l"] for x in org_members])
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
        try:
            repo_data(user, repo, name, org)
        except github.Reauthorize:
            del flask.session["t"]
            del flask.session["i"]
            redirect("/")

    n = 0
    opts = ["collaborators", "contributors", "forkers", "watchers"]
    if org:
        opts += ["org_members"]
    for k in opts:
        if repo[k]:
            n += 1

    if n == 1:
        n = "1"
    elif n:
        n = "1-%s" % n

    return flask.render_template("repo.html", user=user, n=n,
                                 repo=repo, org=org,
                                 **gen_xsrf(["refresh_repo", "create", "logout"]))


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


@app.route("/logout", methods=["POST"])
@check_xsrf("logout")
def logout():
    del flask.session["t"]
    del flask.session["i"]
    return flask.redirect("/")


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


def _create(github_id, usernames, addresses, repo, org):
    return "hello world"


@app.route("/create", methods=["POST"])
@check_xsrf("create")
def create():
    github_id = flask.session.get("i", None)
    email = github_id and db.email(github_id)
    if not email:
        return flask.abort(403, "No email")

    repo = flask.request.form.get("repo")
    org = flask.request.form.get("org")
    usernames = flask.request.form.getlist("username")
    addresses = flask.request.form.getlist("address")
    addresses = [a for a in addresses if valid_email(a)]

    if not addresses and not usernames:
        flask.flash("Please select some list members before creating your list.")
        return flask.redirect(repo_url(repo, org))

    if not fiesta.address(email) or "oauth_token" in db.user(flask.session["i"]):
        try:
            return _create(github_id, usernames, addresses, repo, org)
        except:
            pass

    creds = fiesta.temporary_credentials(flask.request.url_root + "authcreate")
    db.pending_create(creds, github_id, usernames, addresses, repo, org)
    return flask.redirect(fiesta.authorize_url(creds))


@app.route("/authcreate")
def authcreate():
    id = flask.request.args.get("oauth_token")
    verifier = flask.request.args.get("oauth_verifier")
    pending = db.get_pending(id)
    if not id or not verifier or not pending:
        flask.flash("Authentication failed, please try again.")
        return flask.redirect("/")
    temp = {"oauth_token": id, "oauth_token_secret": pending["secret"]}
    token = fiesta.token(temp, verifier)
    if not token:
        flask.flash("Authentication failed, please try again.")
        return flask.redirect("/")
    db.add_fiesta_token(pending["creator_id"], token)
    db.delete_pending(id)
    return _create(pending["creator_id"], pending["usernames"],
                   pending["addresses"], pending["repo"], pending["org"])


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


@app.route("/auth/response")
def auth_response():
    code = flask.request.args.get("code", "")
    token = github.token_for_code(code)
    if token:
        flask.session["t"] = token
    return flask.redirect("/")


@app.route("/favicon.ico")
def favicon():
    return app.send_static_file("i/favicon.ico")


if __name__ == '__main__':
    app.run(debug=True)
