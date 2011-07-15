import base64
import hashlib
import hmac
import time

import coding
import settings


"""Return codes for check_sig."""
OKAY = 0
TIMEOUT = 1
BAD = 2


def no_time_32(message):
    sig = hmac.new(settings.message_key, message, hashlib.sha1)
    return coding.b32enc(sig.digest())


def no_time(message):
    sig = hmac.new(settings.message_key, message, hashlib.sha1)
    return coding.b64enc(sig.digest())


def dns_safe(message):
    sig = hmac.new(settings.message_key, message, hashlib.sha1)
    return base64.b32encode(sig.digest()).lower()


def sign(message):
    created = coding.urlenc_int(int(time.time()))
    sig = no_time(message + created)
    return created + "|" + sig


def check_sig(message, sig, timeout=False):
    """timeout is in seconds."""
    if not sig or "|" not in sig:
        return BAD
    created, sig = sig.split("|", 1)
    if not sig == no_time(message + created):
        return BAD
    if timeout:
        now = time.time()
        if now - timeout > coding.urldec_int(created):
            return TIMEOUT
    return OKAY


def list_size_exempt(list_name):
    return list_name + "+big/" + no_time_32(list_name)[:10]
