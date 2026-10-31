```edit
FILE: src/packaging/markers.py
<<<<<<< SEARCH
        return tuple(canonicalize_name(v) for v in values)
=======
        return tuple(canonicalize_name(v or "") for v in values)
>>>>>>> REPLACE
```