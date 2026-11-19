class TransientError(Exception):
    """An LLM or network failure worth retrying with backoff."""
