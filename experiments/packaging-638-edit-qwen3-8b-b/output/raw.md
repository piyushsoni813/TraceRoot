```edit
FILE: src/packaging/markers.py
<<<<<<< SEARCH
    def evaluate(self, environment: Optional[Dict[str, str]] = None) -> bool:
        """Evaluate a marker.

        Return the boolean from evaluating the given marker against the
        environment. environment is an optional argument to override all or
        part of the determined environment.

        The environment is determined from the current Python process.
        """
        current_environment = default_environment()
        current_environment["extra"] = ""
        if environment is not None:
            current_environment.update(environment)

        return _evaluate_markers(self._markers, current_environment)
=======
    def evaluate(self, environment: Optional[Dict[str, str]] = None) -> bool:
        """Evaluate a marker.

        Return the boolean from evaluating the given marker against the
        environment. environment is an optional argument to override all or
        part of the determined environment.

        The environment is determined from the current Python process.
        """
        current_environment = default_environment()
        if environment is not None:
            current_environment.update(environment)

        # Handle 'extra' specially to avoid None values
        if "extra" in current_environment:
            current_environment["extra"] = canonicalize_name(current_environment["extra"])
        else:
            current_environment["extra"] = ""

        return _evaluate_markers(self._markers, current_environment)
>>>>>>> REPLACE
```