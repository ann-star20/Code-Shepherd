import sys
sys.path.insert(0, "/app/_shared")
from shared.auth import create_access_token
token = create_access_token({"sub": "eval-user", "role": "admin"})
print(token)
