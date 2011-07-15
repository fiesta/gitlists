"""Encoding/decoding stuff."""

import base64
import string

import errors


CHARS = string.digits + string.ascii_letters + "-_"
RADIX = len(CHARS)


def urlenc_int(i):
    if i < 0:
        raise errors.InternalError("bad int for urlenc %r" % i)
    result = ""
    while True:
        i, r = divmod(i, RADIX)
        result = CHARS[r] + result
        if i == 0:
            return result


def urldec_int(s):
    result = 0
    while len(s):
        result *= RADIX
        c = s[0]
        result += CHARS.index(c)
        s = s[1:]
    return result


def b32enc(s):
    return base64.b32encode(s).rstrip("=").lower()


def b32dec(s):
    s = s + "=" * (len(s) % 8)
    return base64.b32decode(s.upper())


def b64enc(s):
    return base64.urlsafe_b64encode(s).rstrip("=")


def b64dec(s):
    s = s + "=" * (len(s) % 4)
    return base64.urlsafe_b64decode(s)
