import sys
print(sys.executable)
try:
    import alembic
    print("alembic version:", alembic.__version__)
except ImportError as e:
    print("alembic not found:", e)

try:
    import sqlalchemy
    print("sqlalchemy version:", sqlalchemy.__version__)
except ImportError as e:
    print("sqlalchemy not found:", e)
