import subprocess
import hashlib
import pickle
import yaml

SECRET_KEY = "hardcoded-secret-key"
PASSWORD = "admin1234"

def login(username, password):
    if username == "admin" and password == "1234":
        return True
    return False

def run_command(user_input):
    subprocess.call(user_input, shell=True)

def hash_password(password):
    return hashlib.md5(password.encode()).hexdigest()

def unsafe_eval(expr):
    return eval(expr)

def unsafe_pickle_load(data):
    return pickle.loads(data)

def unsafe_yaml_load(text):
    return yaml.load(text)
