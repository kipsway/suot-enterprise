"""Verify all .py files compile."""

import os, py_compile

root = "."
errors = []
total = 0
for dirpath, dirnames, filenames in os.walk(root):
    if ".git" in dirnames:
        dirnames.remove(".git")
    if "__pycache__" in dirnames:
        dirnames.remove("__pycache__")
    if ".github" in dirnames:
        dirnames.remove(".github")
    for fn in filenames:
        if fn.endswith(".py"):
            total += 1
            full = os.path.join(dirpath, fn)
            try:
                py_compile.compile(full, doraise=True)
            except py_compile.PyCompileError as e:
                errors.append(full)

print(f"Total: {total} files checked, {len(errors)} errors")
for e in errors:
    print(f"  ERROR: {e}")
if not errors:
    print("All files compile OK!")
