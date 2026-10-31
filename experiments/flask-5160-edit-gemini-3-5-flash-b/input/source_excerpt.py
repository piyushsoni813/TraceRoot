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
