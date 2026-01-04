
import os
import ssl
import certifi
import logging

logger = logging.getLogger(__name__)

def apply_ssl_patch():
    """
    Applies a patch to ensure SSL certificates are properly loaded on macOS
    and other environments where the default certificate store might be missing.
    """
    try:
        # Set SSL_CERT_FILE and REQUESTS_CA_BUNDLE to certifi's bundle
        cert_path = certifi.where()
        os.environ['SSL_CERT_FILE'] = cert_path
        os.environ['REQUESTS_CA_BUNDLE'] = cert_path
        
        # Override default context to use certifi bundle
        # This helps libraries that don't respect SSL_CERT_FILE but use the default context
        original_create_default_context = ssl.create_default_context
        
        def patched_create_default_context(*args, **kwargs):
            context = original_create_default_context(*args, **kwargs)
            context.load_verify_locations(cafile=cert_path)
            return context
        
        # We don't necessarily want to monkeypatch global ssl unless absolutely necessary,
        # but for aiohttp/requests in this specific environment, it's often the most reliable way.
        # Alternatively, we can just return the context and use it in clients.
        
        logger.info(f"SSL patch applied using certifi: {cert_path}")
        return cert_path
    except Exception as e:
        logger.error(f"Failed to apply SSL patch: {e}")
        return None

def get_ssl_context():
    """Returns a secure SSL context using certifi certificates."""
    try:
        context = ssl.create_default_context(cafile=certifi.where())
        return context
    except Exception as e:
        logger.error(f"Failed to create SSL context: {e}")
        return None
