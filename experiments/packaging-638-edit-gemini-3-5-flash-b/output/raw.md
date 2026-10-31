```edit
FILE: src/packaging/markers.py
<<<<<<< SEARCH
def _normalize(*values: str, key: str) -> Tuple[str, ...]:
    # PEP 685 – Comparison of extra names for optional distribution dependencies
    # https://peps.python.org/pep-0685/
    # > When comparing extra names, tools MUST normalize the names being
    # > compared using the semantics outlined in PEP 503 for names
    if key == "extra":
        return tuple(canonicalize_name(v) for v in values)

    # other environment markers don't have such standards
    return values
=======
def _normalize(*values: Optional[str], key: str) -> Tuple[Optional[str], ...]:
    # PEP 685 – Comparison of extra names for optional distribution dependencies
    # https://peps.python.org/pep-0685/
    # > When comparing extra names, tools MUST normalize the names being
    # > compared using the semantics outlined in PEP 503 for names
    if key == "extra":
        return tuple(
            canonicalize_name(v) if v is not None else None for v in values
        )

    # other environment markers don't have such standards
    return values
>>>>>>> REPLACE
```