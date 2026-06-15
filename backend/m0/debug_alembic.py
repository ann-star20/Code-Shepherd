import sys
import os
os.chdir("/tmp")

# Find the real alembic
import alembic
print("alembic location:", alembic.__file__)
print("alembic dir contents:")
import os.path
alembic_dir = os.path.dirname(alembic.__file__)
print(os.listdir(alembic_dir))
