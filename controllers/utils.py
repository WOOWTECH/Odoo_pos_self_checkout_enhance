# -*- coding: utf-8 -*-
import hmac


def safe_token_eq(expected, given):
    """Constant-time comparison of a stored secret with a client value.

    ``hmac.compare_digest`` raises TypeError for ``str`` arguments holding
    non-ASCII characters, which would turn a bad client token into a 500.
    Compare UTF-8 bytes instead; anything that is not a non-empty string
    simply does not match.
    """
    if not expected or not given or not isinstance(expected, str) or not isinstance(given, str):
        return False
    return hmac.compare_digest(
        expected.encode('utf-8', 'surrogateescape'),
        given.encode('utf-8', 'surrogateescape'),
    )
