from automana.core.settings import get_settings


def get_pgp_key() -> str:
    """Return the PGP symmetric key. Raises if unconfigured."""
    key = get_settings().pgp_secret_key
    if not key:
        raise RuntimeError(
            "pgp_secret_key is not configured — set the pgp_secret_key Docker secret "
            "or PGP_SECRET_KEY environment variable"
        )
    return key
