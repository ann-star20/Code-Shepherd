import subprocess
r = subprocess.run(
      ["python", "-m", "pylint", "dev2/tools/python/pylint_tool.py", "--output-format=json", "--score=no"],
      capture_output=True, text=True
  )
print(r.stdout)