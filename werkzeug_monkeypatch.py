import werkzeug.wrappers


def werkzeug_request_repr(req):
    """Monkey-patch for Request __repr__.

    We have this so we can include POST data in the exception emails.
    """
    args = []
    try:
        args.append("'%s'" % req.url)
        args.append('[%s]' % req.method)
        args.append('<%r>' % (req.data or req.form))
    except Exception:
        args.append('(invalid WSGI environ)')

    return '<%s %s>' % (
        req.__class__.__name__,
        ' '.join(args)
        )


werkzeug.wrappers.BaseRequest.__repr__ = werkzeug_request_repr
