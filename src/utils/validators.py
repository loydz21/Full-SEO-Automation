"""Input validation utilities for URLs, emails, and domains."""

import re
from urllib.parse import urlparse


def validate_url(url: str) -> tuple[bool, str]:
    """Validate a URL string.

    Args:
        url: The URL to validate.

    Returns:
        Tuple of (is_valid, error_message).  error_message is empty on success.
    """
    if not url or not isinstance(url, str):
        return False, "URL is empty or not a string."
    url = url.strip()
    try:
        parsed = urlparse(url)
    except Exception as exc:
        return False, f"URL parse error: {exc}"
    if parsed.scheme not in ("http", "https"):
        return False, f"Invalid scheme: {parsed.scheme!r}. Must be http or https."
    if not parsed.netloc:
        return False, "URL has no network location (domain)."
    hostname = parsed.hostname or ""
    if not hostname or len(hostname) > 253:
        return False, "Invalid hostname length."
    return True, ""


def validate_email(email: str) -> tuple[bool, str]:
    """Validate an email address.

    Args:
        email: The email address to validate.

    Returns:
        Tuple of (is_valid, error_message).
    """
    if not email or not isinstance(email, str):
        return False, "Email is empty or not a string."
    email = email.strip()
    pattern = re.compile(
        r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@"
        r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
        r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$"
    )
    if not pattern.match(email):
        return False, "Email format is invalid."
    if len(email) > 320:
        return False, "Email exceeds maximum length (320 chars)."
    domain = email.split("@")[1]
    if "." not in domain:
        return False, "Email domain must contain at least one dot."
    return True, ""


def validate_domain(domain: str) -> tuple[bool, str]:
    """Validate a domain name.

    Args:
        domain: The domain name to validate.  May include protocol prefix.

    Returns:
        Tuple of (is_valid, error_message).
    """
    if not domain or not isinstance(domain, str):
        return False, "Domain is empty or not a string."
    domain = domain.strip().lower()
    # Strip protocol if present
    if "://" in domain:
        domain = domain.split("://", 1)[1]
    # Strip path and port
    domain = domain.split("/")[0]
    domain = domain.split(":")[0]
    if len(domain) > 253:
        return False, "Domain exceeds maximum length (253 chars)."
    if "." not in domain:
        return False, "Domain must contain at least one dot."
    labels = domain.split(".")
    for label in labels:
        if not label:
            return False, "Domain contains empty label (double dot)."
        if len(label) > 63:
            return False, f"Label '{label}' exceeds 63 chars."
        if not re.match(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", label):
            return False, f"Label '{label}' contains invalid characters."
    return True, ""
