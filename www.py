import json
import urlparse

import decorator
import flask

import db
import github
import errors
import fiesta
import settings
import sign


app = flask.Flask(__name__)
app.secret_key = settings.session_key


def _gen_xsrf(action):
    return sign.sign(action + flask.session["g"])


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


@decorator.decorator
def reauthorize(view, *args, **kwargs):
    try:
        return view(*args, **kwargs)
    except github.Reauthorize:
        del flask.session["g"]
        return flask.redirect("/")


@app.route("/")
@reauthorize
def index():
    if "g" in flask.session:
        orgs = github.orgs()
        org_repos = [github.repos(org=org["login"]) for org in orgs]
        return flask.render_template("index_logged_in.html",
                                     user=github.user_info(),
                                     repos=github.repos(),
                                     orgs=orgs, org_repos=org_repos)
    return flask.render_template("index.html", auth_url=github.auth_url())


@reauthorize
def repo_page(user, repos, name, org=None):
    repo = None
    for r in repos:
        if r["name"] == name:
            repo = r
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
                                 watchers=watchers,
                                 **gen_xsrf(["create"]))


@app.route("/repo/<name>")
@reauthorize
def repo(name):
    if "g" not in flask.session:
        return flask.abort(403, "No user")
    return repo_page(github.user_info(), github.repos(), name)


@app.route("/repo/<org_handle>/<name>")
@reauthorize
def org_repo(org_handle, name):
    if "g" not in flask.session:
        return flask.abort(403, "No user")

    for org in github.orgs():
        if org["login"] == org_handle:
            return repo_page(github.user_info(),
                             github.repos(org=org["login"]), name, org)

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


def _create(github_id, usernames, addresses, repo, org):
    return "hello world"


@app.route("/create", methods=["POST"])
@check_xsrf("create")
def create():
    user = github.user_info()

    repo = flask.request.form.get("repo")
    org = flask.request.form.get("org")
    usernames = flask.request.form.getlist("username")
    addresses = flask.request.form.getlist("address")
    addresses = [a for a in addresses if valid_email(a)]

    if not addresses and not usernames:
        flask.flash("Please select some list members before creating your list.")
        return flask.redirect(repo_url(repo, org))

    if not fiesta.address(user["email"]) or flask.session.get("f", None):
        try:
            return _create(user["id"], usernames, addresses, repo, org)
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


@app.route("/auth/github")
def auth_github():
    token = github.token(flask.request.args["code"])
    if token:
        flask.session["g"] = token
    return flask.redirect("/")


@app.route("/auth/fiesta")
def auth_fiesta():
    token = fiesta.get_user_token(flask.request.args["code"])
    raise errors.TODO("do something here")


@app.route("/favicon.ico")
def favicon():
    return app.send_static_file("i/favicon.ico")


if __name__ == '__main__':
    app.run(debug=True)
