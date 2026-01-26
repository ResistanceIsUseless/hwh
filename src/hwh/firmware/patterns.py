"""
Security Analysis Patterns

Regex patterns and lists for detecting security issues in firmware.
"""

# Credential and secret patterns
CREDENTIAL_PATTERNS = {
    # Passwords
    "password_assignment": r'(?i)(password|passwd|pwd|pass)\s*[=:]\s*["\']?([^"\'\s\n]{4,})',
    "password_field": r'(?i)["\']password["\']\s*:\s*["\']([^"\']+)["\']',

    # API Keys and tokens
    "api_key": r'(?i)(api[_-]?key|apikey)\s*[=:]\s*["\']?([a-zA-Z0-9_-]{16,})',
    "secret_key": r'(?i)(secret[_-]?key|secretkey)\s*[=:]\s*["\']?([a-zA-Z0-9_-]{16,})',
    "auth_token": r'(?i)(auth[_-]?token|bearer)\s*[=:]\s*["\']?([a-zA-Z0-9_.-]{20,})',

    # Cloud provider keys
    "aws_access_key": r'AKIA[0-9A-Z]{16}',
    "aws_secret_key": r'(?i)aws[_-]?secret[_-]?access[_-]?key\s*[=:]\s*["\']?([a-zA-Z0-9/+=]{40})',
    "gcp_api_key": r'AIza[0-9A-Za-z_-]{35}',
    "azure_connection": r'(?i)DefaultEndpointsProtocol=https;AccountName=[^;]+;AccountKey=[^;]+',

    # Private keys
    "rsa_private_key": r'-----BEGIN RSA PRIVATE KEY-----',
    "ec_private_key": r'-----BEGIN EC PRIVATE KEY-----',
    "openssh_private_key": r'-----BEGIN OPENSSH PRIVATE KEY-----',
    "generic_private_key": r'-----BEGIN PRIVATE KEY-----',
    "pgp_private_key": r'-----BEGIN PGP PRIVATE KEY BLOCK-----',

    # JWT secrets
    "jwt_secret": r'(?i)(jwt[_-]?secret|jwt[_-]?key)\s*[=:]\s*["\']?([^"\'\s\n]{8,})',

    # Database credentials
    "mysql_conn": r'(?i)mysql://[^:]+:([^@]+)@',
    "postgres_conn": r'(?i)postgres(ql)?://[^:]+:([^@]+)@',
    "mongodb_conn": r'(?i)mongodb(\+srv)?://[^:]+:([^@]+)@',
    "redis_password": r'(?i)redis://[^:]*:([^@]+)@',

    # Generic secrets
    "generic_secret": r'(?i)(secret|token|credential|auth)\s*[=:]\s*["\']([a-zA-Z0-9_-]{16,})["\']',
    "base64_secret": r'(?i)(secret|key|token)\s*[=:]\s*["\']?([A-Za-z0-9+/]{32,}={0,2})["\']?',
}

# Unsafe C functions that may indicate vulnerabilities
UNSAFE_FUNCTIONS = [
    # Buffer overflow risks
    "strcpy",
    "strcat",
    "sprintf",
    "vsprintf",
    "gets",
    "scanf",
    "sscanf",
    "fscanf",

    # Format string vulnerabilities
    "printf",  # when used with user input
    "fprintf",
    "syslog",

    # Command injection risks
    "system",
    "popen",
    "exec",
    "execl",
    "execle",
    "execlp",
    "execv",
    "execve",
    "execvp",
    "fork",

    # Memory issues
    "alloca",
    "realpath",

    # Deprecated/dangerous
    "mktemp",
    "tmpnam",
    "tempnam",
    "getwd",
    "getpass",
]

# Files that often contain sensitive data
INTERESTING_FILES = [
    # System credentials
    "/etc/passwd",
    "/etc/shadow",
    "/etc/group",
    "/etc/sudoers",
    "/etc/master.passwd",

    # SSH configuration
    "/etc/ssh/sshd_config",
    "/etc/ssh/ssh_config",
    "/root/.ssh/authorized_keys",
    "/root/.ssh/id_rsa",
    "/root/.ssh/id_dsa",
    "/root/.ssh/id_ecdsa",
    "/root/.ssh/id_ed25519",

    # Network configuration
    "/etc/hosts",
    "/etc/hostname",
    "/etc/network/interfaces",
    "/etc/wpa_supplicant.conf",
    "/etc/hostapd.conf",

    # Service credentials
    "/etc/ppp/chap-secrets",
    "/etc/ppp/pap-secrets",

    # SSL/TLS
    "/etc/ssl/private/*",
    "/etc/nginx/ssl/*",
    "/etc/apache2/ssl/*",

    # Web server configs
    "/etc/nginx/nginx.conf",
    "/etc/apache2/apache2.conf",
    "/etc/lighttpd/lighttpd.conf",

    # Database configs
    "/etc/mysql/my.cnf",
    "/etc/postgresql/*/main/pg_hba.conf",
    "/var/lib/mysql/*",

    # Application configs
    "/etc/config/*",
    "/tmp/etc/*",
    "/var/etc/*",
]

# File patterns (globs) for interesting files
INTERESTING_FILE_PATTERNS = [
    "*.conf",
    "*.cfg",
    "*.config",
    "*.ini",
    "*.properties",
    "*.key",
    "*.pem",
    "*.crt",
    "*.cer",
    "*.p12",
    "*.pfx",
    "*.jks",
    "*.keystore",
    "*.db",
    "*.sqlite",
    "*.sqlite3",
    "*.sql",
    "*.bak",
    "*.backup",
    "*.old",
    "*.log",
    ".env",
    ".env.*",
    "*.env",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "authorized_keys",
    "known_hosts",
    "htpasswd",
    ".htpasswd",
    "shadow",
    "passwd",
]

# Directories that often contain sensitive files
INTERESTING_DIRS = [
    "/etc",
    "/var/etc",
    "/tmp/etc",
    "/root",
    "/home",
    "/var/www",
    "/srv",
    "/opt",
    "/usr/local/etc",
    "/private/etc",  # macOS
]

# Patterns indicating hardcoded backdoors
BACKDOOR_PATTERNS = {
    "hardcoded_root": r'(?i)root\s*[=:]\s*["\']?toor',
    "admin_admin": r'(?i)admin\s*[=:]\s*["\']?admin',
    "test_password": r'(?i)(password|pass)\s*[=:]\s*["\']?(test|testing|12345|password)',
    "default_creds": r'(?i)(user|username)\s*[=:]\s*["\']?(admin|root|user|guest)',
    "telnet_backdoor": r'(?i)telnetd.*-l\s*/bin/sh',
    "debug_shell": r'(?i)/bin/sh.*-c.*debug',
}

# Network service patterns that may be risky
RISKY_SERVICE_PATTERNS = {
    "telnet_enabled": r'(?i)telnet\s*(enable|start|=\s*1)',
    "ftp_anonymous": r'(?i)anonymous\s*(enable|=\s*1|ftp)',
    "tftp_enabled": r'(?i)tftp\s*(enable|start|=\s*1)',
    "snmp_public": r'(?i)community\s*[=:]\s*["\']?public',
    "snmp_private": r'(?i)community\s*[=:]\s*["\']?private',
    "debug_enabled": r'(?i)debug\s*(=\s*1|=\s*true|enable)',
    "root_login": r'(?i)(PermitRootLogin|root_login)\s*(yes|=\s*1|enable)',
}

# Firmware-specific patterns
FIRMWARE_PATTERNS = {
    "update_url": r'(?i)(update|firmware|upgrade)[_-]?url\s*[=:]\s*["\']?(https?://[^"\'\s]+)',
    "api_endpoint": r'(?i)api[_-]?(url|endpoint|server)\s*[=:]\s*["\']?(https?://[^"\'\s]+)',
    "hardcoded_ip": r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b',
    "mac_address": r'([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})',
}

# Severity levels for different finding types
FINDING_SEVERITY = {
    # Critical - immediate security risk
    "rsa_private_key": "critical",
    "ec_private_key": "critical",
    "openssh_private_key": "critical",
    "generic_private_key": "critical",
    "aws_access_key": "critical",
    "aws_secret_key": "critical",

    # High - significant security issue
    "password_assignment": "high",
    "hardcoded_root": "high",
    "backdoor_patterns": "high",
    "shadow_readable": "high",

    # Medium - potential issue
    "api_key": "medium",
    "generic_secret": "medium",
    "unsafe_function": "medium",
    "telnet_enabled": "medium",

    # Low - informational
    "debug_enabled": "low",
    "hardcoded_ip": "low",
    "interesting_file": "low",
}
