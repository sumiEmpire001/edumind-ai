import os
import secrets

# Ephemeral, test-only signing key; never a production default or committed credential.
os.environ["JWT_SECRET"] = secrets.token_urlsafe(48)
