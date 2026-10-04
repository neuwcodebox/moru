import logging
import sys

from moru.diagnostics import PrivateTracebackFormatter


def test_error_logs_preserve_code_type_and_stack_without_model_echoed_request():
    private_request = "PRIVATE USER REQUEST AND PROMPT"

    def fail():
        raise ValueError(private_request)

    try:
        fail()
    except ValueError:
        record = logging.LogRecord(
            "generation",
            logging.ERROR,
            __file__,
            1,
            "generation failed code=GENERATION_FAILED",
            (),
            sys.exc_info(),
        )
    output = PrivateTracebackFormatter("%(message)s").format(record)
    assert "GENERATION_FAILED" in output
    assert "ValueError" in output
    assert "in fail" in output
    assert private_request not in output
