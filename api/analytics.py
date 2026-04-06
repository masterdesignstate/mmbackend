from posthog import Client
import os
import logging

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    api_key = os.environ.get('POSTHOG_PROJECT_TOKEN', '')
    host = os.environ.get('POSTHOG_HOST', 'https://us.i.posthog.com')
    if api_key:
        _client = Client(project_api_key=api_key, host=host)
    else:
        logger.warning('POSTHOG_PROJECT_TOKEN not set, analytics disabled')
    return _client


def capture(user_id, event, properties=None):
    client = _get_client()
    if not client:
        return
    try:
        client.capture(event, distinct_id=str(user_id), properties=properties or {})
    except Exception as e:
        logger.error(f'PostHog capture error: {e}')
