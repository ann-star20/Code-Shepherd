import sys
import os
os.chdir("/tmp")

# Don't add /app/service to path - that shadows alembic package
sys.path.insert(0, "/app/_shared")
# Only add venv site-packages explicitly
sys.path.insert(0, "/app/.venv/lib/python3.12/site-packages")

import alembic
print("alembic __file__:", alembic.__file__)
print("sys.path:", sys.path[:5])
