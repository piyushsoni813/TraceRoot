You are repairing a Python regression. You have only the bug report, stack
trace, and source excerpt below. Do not assume access to the rest of the repository, tests, Git history, or any
other tools.

Return your fix as edits inside exactly one fenced code block whose info string
is `edit`. Each edit has this exact form:

```edit
FILE: src/flask/scaffold.py
<<<<<<< SEARCH
exact original lines, copied character for character including indentation
=======
the replacement lines
>>>>>>> REPLACE
```

The SEARCH text must match the original code exactly and occur exactly once in
that file. You may put several edits inside the one block. Edits may modify only
files under `src/flask/`. Do not modify, add, or delete tests, dependency files,
configuration, or generated files. Do not include prose outside the code block.

## Bug report

Creating a Flask application in a Python script fails before the development
server starts. The same pattern previously worked. The failure occurs while the
framework determines the application's instance path.

Environment reported by the original reporter:

- Python 3.11.4
- Flask development branch

Expected behavior: constructing the application should succeed and the script
should be able to continue to its server startup code.

## Stack trace

```text
Traceback (most recent call last):
  File "app.py", line 3, in <module>
    app = Flask(__name__)
  File "flask/app.py", line 376, in __init__
    instance_path = self.auto_find_instance_path()
  File "flask/app.py", line 630, in auto_find_instance_path
    prefix, package_path = find_package(self.import_name)
  File "flask/scaffold.py", line 898, in find_package
    package_path = _find_package_path(import_name)
  File "flask/scaffold.py", line 858, in _find_package_path
    spec = importlib.util.find_spec(root_mod_name)
  File "<frozen importlib.util>", line 111, in find_spec
ValueError: __main__.__spec__ is None
```

## Source excerpt

The unmodified code of `src/flask/scaffold.py` containing the functions in the stack trace (lines 816-923):

```python
def _find_package_path(import_name):
    """Find the path that contains the package or module."""
    root_mod_name, _, _ = import_name.partition(".")

    try:
        root_spec = importlib.util.find_spec(root_mod_name)

        if root_spec is None:
            raise ValueError("not found")
    # ImportError: the machinery told us it does not exist
    # ValueError:
    #    - the module name was invalid
    #    - the module name is __main__
    #    - *we* raised `ValueError` due to `root_spec` being `None`
    except (ImportError, ValueError):
        pass  # handled below
    else:
        # namespace package
        if root_spec.origin in {"namespace", None}:
            package_spec = importlib.util.find_spec(import_name)
            if package_spec is not None and package_spec.submodule_search_locations:
                # Pick the path in the namespace that contains the submodule.
                package_path = pathlib.Path(
                    os.path.commonpath(package_spec.submodule_search_locations)
                )
                search_locations = (
                    location
                    for location in root_spec.submodule_search_locations
                    if _path_is_relative_to(package_path, location)
                )
            else:
                # Pick the first path.
                search_locations = iter(root_spec.submodule_search_locations)
            return os.path.dirname(next(search_locations))
        # a package (with __init__.py)
        elif root_spec.submodule_search_locations:
            return os.path.dirname(os.path.dirname(root_spec.origin))
        # just a normal module
        else:
            return os.path.dirname(root_spec.origin)

    # we were unable to find the `package_path` using PEP 451 loaders
    spec = importlib.util.find_spec(root_mod_name)
    loader = spec.loader if spec is not None else None

    if loader is None or root_mod_name == "__main__":
        # import name is not found, or interactive/main module
        return os.getcwd()

    if hasattr(loader, "get_filename"):
        filename = loader.get_filename(root_mod_name)
    elif hasattr(loader, "archive"):
        # zipimporter's loader.archive points to the .zip file.
        filename = loader.archive
    else:
        # At least one loader is missing both get_filename and archive:
        # Google App Engine's HardenedModulesHook, use __file__.
        filename = importlib.import_module(root_mod_name).__file__

    package_path = os.path.abspath(os.path.dirname(filename))

    # If the imported name is a package, filename is currently pointing
    # to the root of the package, need to get the current directory.
    if _matching_loader_thinks_module_is_package(loader, root_mod_name):
        package_path = os.path.dirname(package_path)

    return package_path


def find_package(import_name: str):
    """Find the prefix that a package is installed under, and the path
    that it would be imported from.

    The prefix is the directory containing the standard directory
    hierarchy (lib, bin, etc.). If the package is not installed to the
    system (:attr:`sys.prefix`) or a virtualenv (``site-packages``),
    ``None`` is returned.

    The path is the entry in :attr:`sys.path` that contains the package
    for import. If the package is not installed, it's assumed that the
    package was imported from the current working directory.
    """
    package_path = _find_package_path(import_name)
    py_prefix = os.path.abspath(sys.prefix)

    # installed to the system
    if _path_is_relative_to(pathlib.PurePath(package_path), py_prefix):
        return py_prefix, package_path

    site_parent, site_folder = os.path.split(package_path)

    # installed to a virtualenv
    if site_folder.lower() == "site-packages":
        parent, folder = os.path.split(site_parent)

        # Windows (prefix/lib/site-packages)
        if folder.lower() == "lib":
            return parent, package_path

        # Unix (prefix/lib/pythonX.Y/site-packages)
        if os.path.basename(parent).lower() == "lib":
            return os.path.dirname(parent), package_path

        # something else (prefix/site-packages)
        return site_parent, package_path

    # not installed
    return None, package_path
```
