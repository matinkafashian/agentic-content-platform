import logging
import re
from typing import Any

_KEY_VALUE_SECRET = re.compile(
    r"(?i)(?P<key>(?:[a-z0-9]+[_-])*(?:token|api[_-]?key|authorization|password|secret))"
    r"(?P<separator>\s*[:=]\s*)"
    r"(?P<value>\"[^\"]*\"|'[^']*'|Bearer\s+[^\s,;]+|[^\s,;]+)"
)
_OPENAI_STYLE_SECRET = re.compile(r"(?i)(?<![a-z0-9])sk-[a-z0-9_-]+")
_factory_installed = False


def redact_secrets(message: str) -> str:
    redacted = _KEY_VALUE_SECRET.sub(
        lambda match: f"{match.group('key')}{match.group('separator')}[REDACTED]",
        message,
    )
    return _OPENAI_STYLE_SECRET.sub("[REDACTED]", redacted)


class SecretRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            rendered = record.getMessage()
        except Exception:
            rendered = str(record.msg)
        record.msg = redact_secrets(rendered)
        record.args = ()
        return True


def _install_redacting_record_factory() -> None:
    global _factory_installed
    if _factory_installed:
        return

    previous_factory = logging.getLogRecordFactory()

    def redacting_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = previous_factory(*args, **kwargs)
        SecretRedactionFilter().filter(record)
        return record

    logging.setLogRecordFactory(redacting_factory)
    _factory_installed = True


def configure_logging(*, debug: bool) -> None:
    _install_redacting_record_factory()
    level = logging.DEBUG if debug else logging.INFO
    root = logging.getLogger()
    root.setLevel(level)

    for handler in root.handlers:
        handler.addFilter(SecretRedactionFilter())

    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S%z",
            )
        )
        handler.addFilter(SecretRedactionFilter())
        root.addHandler(handler)

    logging.getLogger("app").setLevel(level)
