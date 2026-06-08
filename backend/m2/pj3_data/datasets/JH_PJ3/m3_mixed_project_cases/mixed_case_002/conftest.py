import os
import sys

# 케이스 루트를 sys.path에 추가해 `from app...` import가 동작하도록 한다.
sys.path.insert(0, os.path.dirname(__file__))
