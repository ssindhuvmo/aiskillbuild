import anthropic

from core.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL

MODEL = ANTHROPIC_MODEL


class LLMUnavailable(Exception):
    pass


def get_client() -> anthropic.Anthropic:
    if not ANTHROPIC_API_KEY:
        raise LLMUnavailable("ANTHROPIC_API_KEY is not set. Add it to backend/.env and restart the server.")
    # The SDK retries transient errors (429/5xx/connection) with backoff.
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, max_retries=3)


def friendly_error(exc: Exception) -> str:
    if isinstance(exc, LLMUnavailable):
        return str(exc)
    if isinstance(exc, anthropic.AuthenticationError):
        return "The Anthropic API key was rejected. Check ANTHROPIC_API_KEY in backend/.env."
    if isinstance(exc, anthropic.RateLimitError):
        return "The AI service is rate-limited right now. Please try again in a moment."
    if isinstance(exc, anthropic.APIConnectionError):
        return "Could not reach the AI service. Check your network connection and try again."
    if isinstance(exc, anthropic.APIStatusError):
        return f"The AI service returned an error ({exc.status_code}). Please try again."
    return "Something went wrong while generating a reply. Please try again."
