"""Sends logs, traces and a 'tokens per request' metric to Application Insights."""

import logging

logger = logging.getLogger("chatbot")
_token_histogram = None


def setup_telemetry(connection_string: str) -> None:
    global _token_histogram
    logging.basicConfig(level=logging.INFO)
    if not connection_string:
        logger.info("Application Insights not configured; telemetry is off.")
        return
    from azure.monitor.opentelemetry import configure_azure_monitor
    from opentelemetry import metrics

    configure_azure_monitor(connection_string=connection_string, logger_name="chatbot")
    meter = metrics.get_meter("chatbot")
    _token_histogram = meter.create_histogram(
        "chat_tokens_per_request", unit="tokens", description="Tokens used per chat"
    )


def record_tokens(total_tokens: int) -> None:
    if _token_histogram is not None and total_tokens > 0:
        _token_histogram.record(total_tokens)
