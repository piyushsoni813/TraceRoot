```edit
FILE: src/packaging/utils.py
<<<<<<< SEARCH
def canonicalize_name(name):
    value = _canonicalize_regex.sub("-", name).lower()
    return value
=======
def canonicalize_name(name):
    if name is None:
        return None
    value = _canonicalize_regex.sub("-", name).lower()
    return value
>>>>>>> REPLACE
```