import configparser
import os
from configparser import RawConfigParser
from urllib.parse import quote_plus

config = RawConfigParser()
config_path = os.path.join(os.path.dirname(__file__), 'settings.ini')
config.read(config_path)

# ── Execution environment ────────────────────────────────────────────────────
# Every reader below falls back to the LOCAL default when the section/option is
# missing, so an settings.ini that predates these sections keeps behaving
# exactly as it did before.

def get_execution_type():
    """
    'local' or 'azure'.

    The IQEA_EXECUTION_TYPE environment variable wins over settings.ini so the
    same image can be repointed from the Azure portal without a rebuild. Any
    unrecognised value falls back to 'local' — the safe direction, since local
    is the behaviour that already works.
    """
    value = (os.environ.get('IQEA_EXECUTION_TYPE')
             or config.get('EXECUTION', 'execution_type', fallback='local'))
    value = (value or '').strip().lower()
    return value if value in ('local', 'azure') else 'local'


def is_azure():
    return get_execution_type() == 'azure'


def is_local():
    return get_execution_type() == 'local'


# ── Browser (azure only — local ignores all of these) ────────────────────────

def get_selenium_remote_url():
    return os.environ.get('SELENIUM_REMOTE_URL') or config.get(
        'BROWSER', 'selenium_remote_url', fallback='http://chrome:4444/wd/hub')


def get_novnc_password():
    """
    VNC password to hand the noVNC client so the user is not prompted.

    Note this must match the CHROME SIDECAR's SE_VNC_PASSWORD. The app cannot
    read the sidecar's environment, which is why it is configured here rather
    than picked up automatically. Blank means the sidecar runs with
    SE_VNC_NO_PASSWORD=true and no password is needed.
    """
    value = os.environ.get('IQEA_NOVNC_PASSWORD')
    if value is None:
        value = config.get('BROWSER', 'novnc_password', fallback='secret')
    return (value or '').strip()


def get_novnc_path():
    return os.environ.get('IQEA_NOVNC_PATH') or config.get(
        'BROWSER', 'novnc_path', fallback='/vnc/')


def get_window_size():
    """Returns (width, height) as ints."""
    raw = config.get('BROWSER', 'window_size', fallback='1920,1080')
    try:
        width, height = [int(x.strip()) for x in raw.split(',')[:2]]
        return width, height
    except (ValueError, IndexError):
        return 1920, 1080


def get_browser_pool_size():
    try:
        return max(1, int(config.get('BROWSER', 'browser_pool_size', fallback='1')))
    except ValueError:
        return 1


def get_session_timeout_mins():
    try:
        return max(1, int(config.get('BROWSER', 'session_timeout_mins', fallback='30')))
    except ValueError:
        return 30


def get_recorder_poll_secs():
    """
    Seconds between recorder monitor-thread polls.

    Defaults differ by environment: 2s locally (unchanged from the hardcoded
    value it replaces) and 5s in azure, where every poll is an HTTP round trip
    to a shared Grid and there may be many people recording at once.
    """
    raw = config.get('BROWSER', 'recorder_poll_secs', fallback='').strip()
    if raw:
        try:
            return max(0.5, float(raw))
        except ValueError:
            pass
    return 5.0 if is_azure() else 2.0


def debug_logs_enabled():
    """
    Per-poll debug printing from the recorder threads.

    On locally (unchanged behaviour), off in azure unless explicitly enabled —
    the recorder prints a block per thread per poll, which multiplied by the
    number of concurrent users would dominate the Azure log stream and bill.
    """
    raw = config.get('EXECUTION', 'debug_logs', fallback='').strip().lower()
    if raw in ('true', '1', 'yes'):
        return True
    if raw in ('false', '0', 'no'):
        return False
    return not is_azure()


# ── OCR ──────────────────────────────────────────────────────────────────────

def get_tesseract_cmd():
    """Absolute path to the tesseract binary, or '' to resolve from PATH."""
    return (os.environ.get('TESSERACT_CMD')
            or config.get('OCR', 'tesseract_cmd', fallback='')).strip()


def prefer_vision_ocr():
    return config.get('OCR', 'prefer_vision_ocr',
                      fallback='false').strip().lower() in ('true', '1', 'yes')


def get_source():
    return config.get('GENERAL', 'source')  # source can be 'file' or 'database'
def get_model():
    return config.get('GENERAL', 'model')
# ── Application database (MySQL) ─────────────────────────────────────────────
# One MySQL server per execution environment, picked by get_execution_type():
# [DATABASE_local] for a workstation, [DATABASE_azure] for the container. The
# same code path serves both — only the section changes — so there is no
# "azure only" branch to keep in step with the local one.
#
# Every value can be overridden by an environment variable (IQEA_DB_HOST,
# IQEA_DB_USER, IQEA_DB_PASSWORD, IQEA_DB_NAME, IQEA_DB_PORT). In Azure, set
# those as App Service application settings instead of committing the cloud
# credentials to settings.ini, which is shared through git.

def _db_section():
    """The settings.ini section for this environment, with a fallback to the
    plain [DATABASE] section so an older ini keeps working."""
    section = 'DATABASE_azure' if is_azure() else 'DATABASE_local'
    return section if config.has_section(section) else 'DATABASE'


def _db_setting(option, env_var, fallback=''):
    return (os.environ.get(env_var)
            or config.get(_db_section(), option, fallback=fallback)).strip()


def get_db_config():
    """The resolved connection settings as a dict — used by the connection
    string, and by the migration tooling that needs the parts separately."""
    return {
        'host': _db_setting('DB_HOST', 'IQEA_DB_HOST', '127.0.0.1'),
        'port': int(_db_setting('DB_PORT', 'IQEA_DB_PORT', '3306') or 3306),
        'user': _db_setting('DB_USER', 'IQEA_DB_USER', 'root'),
        'password': _db_setting('DB_PASSWORD', 'IQEA_DB_PASSWORD', ''),
        'database': _db_setting('DB_NAME', 'IQEA_DB_NAME', 'iqea'),
        'ssl_disabled': _db_setting('DB_SSL_DISABLED', 'IQEA_DB_SSL_DISABLED',
                                    'True').lower() in ('true', '1', 'yes'),
    }


def get_db_url(include_database=True):
    """
    SQLAlchemy URL for the application database.

    The password is percent-encoded here rather than expected pre-encoded in the
    ini. The old PostgreSQL entry stored it already escaped ("Automation%40123"),
    which only worked because whoever wrote it did the escaping by hand — the
    MySQL passwords contain '@', and an unescaped one silently truncates the URL
    at the wrong place and produces a confusing "unknown host" error.

    include_database=False yields a server-level URL, for creating the database
    itself before any table exists.
    """
    cfg = get_db_config()
    password = quote_plus(cfg['password'])
    user = quote_plus(cfg['user'])
    target = cfg['database'] if include_database else ''

    url = (f"mysql+pymysql://{user}:{password}"
           f"@{cfg['host']}:{cfg['port']}/{target}?charset=utf8mb4")

    # Azure Database for MySQL accepts plaintext when the server's
    # require_secure_transport is OFF, which is what DB_SSL_DISABLED records.
    # When it is on, pymysql needs to be told to negotiate TLS.
    if not cfg['ssl_disabled']:
        url += "&ssl=true"

    return url

def get_update_user():
    """Name stamped on rows this app writes.

    Prefer utilities.identity.current_user(), which layers a real session user
    over this. Kept because a number of call sites still import it directly.
    """
    return (_db_setting('DB_UPDATE_USER', 'IQEA_DB_UPDATE_USER')
            or get_db_config()['user'])

def get_api_key():
    return config.get('API', 'Api_key')
def get_xpath_key():
    raw = config.get("XPATH", "allowed_tags")
    allowed_tags = [x.strip() for x in raw.split(",") if x.strip()]
    print("xpath_allowed_tags",allowed_tags)
    return allowed_tags

