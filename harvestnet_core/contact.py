"""A household's optional email address and the links in its pickup emails.

Decided (user, October 11, 2026): pickup messages go by email through n8n and Amazon SES,
not SMS. The address is optional, used only for pickup messages, never returned by the API,
never logged, and deleted with its request after 7 days (design section 12).
"""
import re
from urllib.parse import quote, urlencode

# One "@", a plain local part, and a dotted domain with a letter TLD. Deliberately strict:
# no spaces, quotes, angle brackets, commas or line breaks, so an address can never carry
# a second recipient or an email header.
_LOCAL = re.compile(r"^[A-Za-z0-9.!#$%&*+/=?^_`{|}~-]{1,64}$")
_LABEL = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
_TLD = re.compile(r"^[A-Za-z]{2,63}$")


def email_address(raw):
    """The address, trimmed with its domain lowercased, or ``ValueError``.

    The error never repeats the address, so a bad one never reaches a log.
    """
    if not isinstance(raw, str):
        raise ValueError("email must be text")
    value = raw.strip()
    if not value or len(value) > 254 or value.count("@") != 1:
        raise ValueError("email doesn't look like an email address")
    local, domain = value.split("@")
    labels = domain.split(".")
    if (not _LOCAL.match(local) or local.startswith(".") or local.endswith(".") or ".." in local
            or len(labels) < 2 or not all(_LABEL.match(label) for label in labels) or not _TLD.match(labels[-1])):
        raise ValueError("email doesn't look like an email address")
    return f"{local}@{domain.lower()}"


def release_url(household_page_url, pickup_id, request_code, language="en"):
    """The email's "Can't make it" link: the household page, opened on this pickup.

    The pickup and code ride in the URL fragment, which browsers never send to a server, so
    they stay out of web server logs. Opening the link changes nothing: the page shows the
    pickup, and only a tap on "Can't make it" calls ``release_pickup`` (an email scanner that
    follows links can't release anyone's food).
    """
    if not household_page_url or not pickup_id or not request_code:
        raise ValueError("a release link needs the household page URL, the pickup and its request code")
    base = household_page_url.split("#", 1)[0]
    if not base.endswith("/"):
        base += "/"
    fragment = urlencode({"pickup": pickup_id, "code": request_code, "lang": language}, quote_via=quote)
    return f"{base}#{fragment}"
