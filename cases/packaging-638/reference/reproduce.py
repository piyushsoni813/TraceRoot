"""Evaluator-only reproduction derived from pypa/packaging issue 638. Exit 0 means fixed."""
from packaging.markers import Marker

marker = Marker('extra == "opt-feature"')
result = marker.evaluate({"extra": None})
assert result is False, result
print(result)
