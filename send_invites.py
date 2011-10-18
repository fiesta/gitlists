#!/usr/bin/env python

import smtplib

import db
import github
import settings


def send_invite(username):
    user = github.user_info(username)
    if not user.get("email", None):
        print "No public email: " + username
        return

    first_name, _, _ = user["name"].partition(" ")
    if len(first_name) < 2:
        first_name = username

    message = """From: Mike Dirolf <mike@corp.fiesta.cc>
To: %s
Subject: Welcome to Gitlists
Content-Type: text/plain

Hi %s,

Thanks for joining the Gitlists beta. Gitlists is a simple way to communicate about your Github projects. You can give it a try here:
https://gitlists.com/top_secret

We always love feedback, but during the beta it's especially important. This is my personal address so please reply with any questions, feedback, or suggestions.

Hope you're having a great day,
Mike

P.S. Gitlists is also open source. If you want to hack on it:
https://github.com/fiesta/gitlists
""" % (user["email"], first_name)

    smtp = smtplib.SMTP(settings.relay_host, settings.relay_port)
    smtp.sendmail("mike@corp.fiesta.cc", [user["email"]], message)
    smtp.quit()


if __name__ == "__main__":
    for x in list(db.db.beta.find({"invited": {"$exists": False}})):
        x["invited"] = True
        db.db.beta.save(x)
        print "inviting", x["gh"]
        send_invite(x["gh"])
