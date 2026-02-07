import secrets
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from config.settings import AUTH_TOKEN


bearer = HTTPBearer(auto_error=False)

def require_token(
    creds: HTTPAuthorizationCredentials = Depends(bearer),
) -> None:
    if not AUTH_TOKEN:
        # fail closed if misconfigured
        raise HTTPException(status_code=500, detail="AUTH_TOKEN is not configured")

    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # constant-time compare to avoid timing leaks
    if not secrets.compare_digest(creds.credentials, AUTH_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )