```diff
diff --git a/src/flask/scaffold.py b/src/flask/scaffold.py
index 1234567..89abcde 100644
--- a/src/flask/scaffold.py
+++ b/src/flask/scaffold.py
@@ -858,7 +858,7 @@ def _find_package_path(import_name):
         if root_spec.origin in {"namespace", None}:
             package_spec = importlib.util.find_spec(import_name)
             if package_spec is not None and package_spec.submodule_search_locations:
-                package_path = pathlib.Path(os.path.commonpath(package_spec.submodule_search_locations))
+                package_path = pathlib.Path(os.path.commonpath(package_spec.submodule_search_locations))
                 search_locations = (
                     location
                     for location in root_spec.submodule_search_locations
```