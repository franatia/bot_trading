import re


def validate_name(i: str):
    return True if isinstance(i, str) else False


def validate_email(i: str):
    return True if isinstance(i, str) and ('@' in i) else False


def validate_password(i: str):
    return bool(re.match(pattern="[A-Za-z0-9]", string=i))


def validate_keys(uk: str, sk: str):
    return True if isinstance(uk, str) and isinstance(sk, str) else False


def validate_profile_photo(pp: str):
    return True if isinstance(pp, str) else False
