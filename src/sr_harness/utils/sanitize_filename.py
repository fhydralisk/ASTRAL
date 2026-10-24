import re


def sanitize_filename(value: str) -> str:
    """Replace unsafe path characters in ``value`` with underscores to produce a safe single-component filename.

    Args:
        value: Raw candidate filename string.

    Returns:
        str: Sanitized filename guaranteed not to be empty, ``"."``, or ``".."``.
    """
    value = re.compile(r'[ <>:"/\\|?*\x00-\x1f]').sub("_", value.strip())
    return (value or "unnamed")[:255]
