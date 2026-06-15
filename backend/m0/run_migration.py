import sys
import os

# Must run from /tmp to avoid local alembic/ dir shadowing the installed package
os.chdir("/tmp")

# Add service dir to path for alembic.ini resolution
sys.path.insert(0, "/app/_shared")
sys.path.insert(0, "/app/service")

# Remove the service dir from cwd-based import (we added it to sys.path explicitly)
# but keep /app/.venv site-packages
import site
site_pkgs = [p for p in sys.path if ".venv" in p and "site-packages" in p]
print("site-packages:", site_pkgs)

from alembic.config import Config
from alembic import command

alembic_cfg = Config("/app/service/alembic.ini")
alembic_cfg.set_main_option("script_location", "/app/service/alembic")
command.upgrade(alembic_cfg, "head")
print("Migration complete.")
