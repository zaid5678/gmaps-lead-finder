"""
Shared helper to check an email's domain actually has mail servers before
sending — catches typo'd domains in scraped source data (e.g. a business's
own Google Maps or NHS listing has a misspelled mailto: link) so we don't
waste sends on addresses that will just bounce and hurt sender reputation.
"""

import dns.resolver

_mx_cache: dict[str, bool] = {}


def has_valid_mx(email: str) -> bool:
    """True if the email's domain has MX (or fallback A) records — i.e. mail
    could plausibly be delivered. Caches per-domain to avoid repeat lookups."""
    domain = email.strip().rsplit("@", 1)[-1].lower()
    if domain in _mx_cache:
        return _mx_cache[domain]

    valid = False
    try:
        dns.resolver.resolve(domain, "MX", lifetime=5)
        valid = True
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        try:
            dns.resolver.resolve(domain, "A", lifetime=5)
            valid = True   # no MX but domain resolves — some small setups rely on A record fallback
        except Exception:
            valid = False
    except Exception:
        # Timeout / no nameservers reachable — don't penalise on a transient lookup failure
        valid = True

    _mx_cache[domain] = valid
    return valid
