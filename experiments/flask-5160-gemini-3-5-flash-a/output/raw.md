```diff
--- a/src/flask/scaffold.py
+++ b/src/flask/scaffold.py
@@ -856,7 +856,7 @@
 
     try:
         spec = importlib.util.find_spec(root_mod_name)
-    except ImportError:
+    except (ImportError, ValueError):
         spec = None
 
     if spec is None:
```