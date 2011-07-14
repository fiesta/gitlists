import flask

import github
import settings


app = flask.Flask(__name__)
app.secret_key = settings.session_key


@app.route("/")
def index():
    return flask.render_template("index.html")


@app.route("/auth/request")
def auth_request():
    return flask.redirect(github.auth_url())


@app.route("/auth/response")
def auth_response():
    code = flask.request.args.get("code", "")
    token = github.token_for_code(code)
    return token



if __name__ == '__main__':
    app.run(debug=True)
