import logging

from app.core.logging import SecretRedactionFilter, configure_logging


def test_logs_redact_token_like_values(caplog):
    configure_logging(debug=True)
    logger = logging.getLogger("app.test")

    with caplog.at_level(logging.INFO):
        logger.info(
            "bot_token=%s api_key=%s authorization=%s",
            "123456:secret",
            "sk-sensitive",
            "Bearer private-credential",
        )

    combined = " ".join(record.getMessage() for record in caplog.records)
    assert "123456:secret" not in combined
    assert "sk-sensitive" not in combined
    assert "private-credential" not in combined
    assert combined.count("[REDACTED]") >= 3


def test_logs_preserve_non_sensitive_business_context(caplog):
    configure_logging(debug=False)
    logger = logging.getLogger("app.catalog")

    with caplog.at_level(logging.INFO):
        logger.info("product_id=%s status=%s", 42, "created")

    assert "product_id=42 status=created" in caplog.text


def test_redaction_does_not_consume_third_party_formatter_arguments():
    record = logging.LogRecord(
        name="uvicorn.error",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Started server process [%d]",
        args=(23040,),
        exc_info=None,
    )
    record.color_message = "Started server process [%d]"

    SecretRedactionFilter().filter(record)

    assert record.args == (23040,)
    assert record.color_message % record.args == "Started server process [23040]"
