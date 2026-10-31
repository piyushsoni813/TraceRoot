```edit
FILE: src/flask/scaffold.py
<<<<<<< SEARCH
    def _find_package_path(import_name):
        root_mod_name = import_name.split('.')[0]
        spec = importlib.util.find_spec(root_mod_name)
        if spec is None:
            return None
        return os.path.dirname(spec.origin)
=======
    def _find_package_path(import_name):
        root_mod_name = import_name.split('.')[0]
        if import_name == '__main__':
            return os.path.abspath(sys.argv[0])
        spec = importlib.util.find_spec(root_mod_name)
        if spec is None:
            return None
        return os.path.dirname(spec.origin)
>>>>>>> REPLACE
```