
BEGIN;

INSERT INTO scan_executions (
    task_id,
    trace_id,
    pr_id,
    developer_id,
    execution_ms
)
VALUES (
    'mock-security-scan-task',
    'local-trace-001',
    'local-pr-001',
    'dev2',
    NULL
)
RETURNING id AS scan_id \gset


INSERT INTO scan_issues (
    scan_id,
    agent,
    severity,
    rule_id,
    file,
    line,
    message,
    suggestion,
    similar_issues,
    is_false_positive
)
VALUES
(
    :scan_id,
    'bandit',
    'Minor',
    'B404',
    'mock_vulnerable\auth.py',
    1,
    'Consider possible security implications associated with the subprocess module.',
    'blacklist / https://bandit.readthedocs.io/en/1.9.4/blacklists/blacklist_imports.html#b404-import-subprocess',
    '[]'::jsonb,
    false
),
(
    :scan_id,
    'bandit',
    'Minor',
    'B403',
    'mock_vulnerable\auth.py',
    3,
    'Consider possible security implications associated with pickle module.',
    'blacklist / https://bandit.readthedocs.io/en/1.9.4/blacklists/blacklist_imports.html#b403-import-pickle',
    '[]'::jsonb,
    false
),
(
    :scan_id,
    'bandit',
    'Minor',
    'B105',
    'mock_vulnerable\auth.py',
    6,
    'Possible hardcoded password: ''hardcoded-secret-key''',
    'hardcoded_password_string / https://bandit.readthedocs.io/en/1.9.4/plugins/b105_hardcoded_password_string.html',
    '[]'::jsonb,
    false
),
(
    :scan_id,
    'bandit',
    'Minor',
    'B105',
    'mock_vulnerable\auth.py',
    7,
    'Possible hardcoded password: ''admin1234''',
    'hardcoded_password_string / https://bandit.readthedocs.io/en/1.9.4/plugins/b105_hardcoded_password_string.html',
    '[]'::jsonb,
    false
),
(
    :scan_id,
    'bandit',
    'Minor',
    'B105',
    'mock_vulnerable\auth.py',
    10,
    'Possible hardcoded password: ''1234''',
    'hardcoded_password_string / https://bandit.readthedocs.io/en/1.9.4/plugins/b105_hardcoded_password_string.html',
    '[]'::jsonb,
    false
),
(
    :scan_id,
    'bandit',
    'Critical',
    'B602',
    'mock_vulnerable\auth.py',
    15,
    'subprocess call with shell=True identified, security issue.',
    'subprocess_popen_with_shell_equals_true / https://bandit.readthedocs.io/en/1.9.4/plugins/b602_subprocess_popen_with_shell_equals_true.html',
    '[]'::jsonb,
    false
),
(
    :scan_id,
    'bandit',
    'Critical',
    'B324',
    'mock_vulnerable\auth.py',
    18,
    'Use of weak MD5 hash for security. Consider usedforsecurity=False',
    'hashlib / https://bandit.readthedocs.io/en/1.9.4/plugins/b324_hashlib.html',
    '[]'::jsonb,
    false
),
(
    :scan_id,
    'bandit',
    'Major',
    'B307',
    'mock_vulnerable\auth.py',
    21,
    'Use of possibly insecure function - consider using safer ast.literal_eval.',
    'blacklist / https://bandit.readthedocs.io/en/1.9.4/blacklists/blacklist_calls.html#b307-eval',
    '[]'::jsonb,
    false
),
(
    :scan_id,
    'bandit',
    'Major',
    'B301',
    'mock_vulnerable\auth.py',
    24,
    'Pickle and modules that wrap it can be unsafe when used to deserialize untrusted data, possible security issue.',
    'blacklist / https://bandit.readthedocs.io/en/1.9.4/blacklists/blacklist_calls.html#b301-pickle',
    '[]'::jsonb,
    false
),
(
    :scan_id,
    'bandit',
    'Major',
    'B506',
    'mock_vulnerable\auth.py',
    27,
    'Use of unsafe yaml load. Allows instantiation of arbitrary objects. Consider yaml.safe_load().',
    'yaml_load / https://bandit.readthedocs.io/en/1.9.4/plugins/b506_yaml_load.html',
    '[]'::jsonb,
    false
);


INSERT INTO scan_summaries (
    scan_id,
    agent,
    critical,
    major,
    minor
)
VALUES (
    :scan_id,
    'bandit',
    2,
    3,
    5
);

COMMIT;

SELECT :scan_id AS saved_scan_id;
