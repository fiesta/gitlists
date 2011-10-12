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


@app.route("/")
@github.reauthorize
def index():
    if "g" in flask.session:
        orgs = github.orgs()
        org_repos = [github.repos(org=org["login"]) for org in orgs]
        return flask.render_template("index_logged_in.html",
                                     user=github.user_info(),
                                     repos=github.repos(),
                                     orgs=orgs, org_repos=org_repos)
    return flask.render_template("index.html", auth_url=github.auth_url())


@github.authorized
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
                                 watchers=watchers)


@app.route("/repo/<name>")
@github.authorized
def repo(name):
    if "g" not in flask.session:
        return flask.abort(403, "No user")
    return repo_page(github.user_info(), github.repos(), name)


@app.route("/repo/<org_handle>/<name>")
@github.authorized
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


@app.route("/create", methods=["GET"])
@github.authorized
@fiesta.authorize
def create_get():
    repo = flask.request.args.get("repo")
    org = flask.request.args.get("org")

    usernames = flask.request.args.getlist("username")
    addresses = flask.request.args.getlist("address")
    addresses = [a for a in addresses if valid_email(a)]

    if not addresses and not usernames:
        flask.flash("Please select some list members before creating your list.")
        return flask.redirect(repo_url(repo, org))

    return flask.render_template("create.html", user=github.user_info(),
                                 repo=repo, org=org, usernames=usernames,
                                 addresses=addresses, **gen_xsrf(["create"]))


@app.route("/create", methods=["POST"])
@github.authorized
@check_xsrf("create")
def create_post():
    user = github.user_info()

    repo = flask.request.form.get("repo")
    org = flask.request.form.get("org")
    usernames = flask.request.form.getlist("username")
    addresses = flask.request.form.getlist("address")
    addresses = dict([(a, None) for a in addresses if valid_email(a)])

    if not addresses and not usernames:
        flask.flash("Please select some list members before creating your list.")
        return flask.redirect(repo_url(repo, org))

    github_url = "https://github.com/%s/%s" % (org or user["login"], repo)
    description = "Gitlist for " + github_url
    welcome_message = {"subject": "Welcome to %s@gitlists.com" % repo,
                       "markdown": """
[%s](%s) added you to a Gitlist for [%s](%s). Gitlists are dead-simple mailing lists for Github projects. You can create your own at [gitlists.com](https://gitlists.com).

Use %s@gitlists.com to email the list. Use the "List members" link below to see, add or remove list members. Use the "Unsubscribe" link below if you don't want to receive any messages from this list.
""" % (user["login"], "http://github.com/" + user["login"],
       repo, github_url,
       repo)}

    creator = {"group_name": repo,
               "address": user["email"],
               "display_name": user["name"],
               "welcome_message": welcome_message}
    response = fiesta.json_request("/group", {"creator": creator,
                                              "domain": "gitlists.com",
                                              "description": description})
    pending = response["status"]["code"] == 202
    group_id = response["data"]["group_id"]

    for app in flask.request.form.getlist("app"):
        if app == "public":
            data = {"application_id": "public",
                    "options": {"group_name": repo}}
            fiesta.json_request("/group/%s/application" % group_id, data)

    # Subject prefix & archive are on by default, for now
    data = {"application_id": "subject_prefix",
            "options": {"prefix": repo}}
    fiesta.json_request("/group/%s/application" % group_id, data)

    data = {"application_id": "archive"}
    fiesta.json_request("/group/%s/application" % group_id, data)

    for address in addresses:
        data = {"group_name": repo,
                "address": address,
                "welcome_message": welcome_message}
        fiesta.json_request("/membership/" + group_id, data)

    for username in usernames:
        member_user = github.user_info(username)["user"]
        data = {"group_name": repo,
                "address": member_user["email"],
                "display_name": member_user["name"],
                "welcome_message": welcome_message}
        fiesta.json_request("/membership/" + group_id, data)

    if pending:
        flask.flash("Please check your '%s' inbox to confirm your gitlist." % user["email"])
    else:
        flask.flash("You should receive a welcome message at '%s'." % user["email"])
    return flask.redirect("/")


@app.route("/auth/github")
def auth_github():
    return github.finish_auth()


@app.route("/auth/fiesta")
def auth_fiesta():
    return fiesta.finish_auth()


@app.route("/favicon.ico")
def favicon():
    return app.send_static_file("i/favicon.ico")


if __name__ == '__main__':
    app.run(debug=True)
