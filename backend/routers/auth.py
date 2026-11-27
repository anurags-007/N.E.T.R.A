from datetime import datetime, timedelta, timezone
import secrets
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from jose import JWTError, jwt

from backend.database import get_db
from backend import config, models, schemas
from backend.utils import security
from backend.utils.audit import record_audit_log
from backend.utils.limiter import limiter
from backend.utils.validation import validate_password_strength

router = APIRouter(
    prefix="/auth",
    tags=["authentication"]
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token", auto_error=False)


def _set_auth_cookies(response: Response, access_token: str) -> None:
    """Set HttpOnly SameSite=Strict session cookie and readable CSRF cookie."""
    is_prod = config.ENVIRONMENT == "production"
    max_age = security.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    csrf_val = secrets.token_urlsafe(32)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=is_prod,
        samesite="strict",
        max_age=max_age,
        path="/",
    )
    response.set_cookie(
        key="csrf_token",
        value=csrf_val,
        httponly=False,
        secure=is_prod,
        samesite="strict",
        max_age=max_age,
        path="/",
    )


def _extract_token(request: Request, bearer_token: Optional[str]) -> tuple[Optional[str], bool]:
    """Return (jwt_token, used_cookie). Prefers HttpOnly cookie when present."""
    cookie_token = request.cookies.get("access_token")
    if cookie_token and not bearer_token:
        return cookie_token, True
    return bearer_token or cookie_token, False


def _prune_expired_blocklist(db: Session) -> None:
    """Remove expired JWT jti entries so TokenBlocklist stays bounded."""
    now = datetime.now(timezone.utc)
    db.query(models.TokenBlocklist).filter(
        models.TokenBlocklist.expires_at.isnot(None),
        models.TokenBlocklist.expires_at < now,
    ).delete(synchronize_session=False)


async def get_current_user(
    request: Request,
    bearer_token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token, used_cookie = _extract_token(request, bearer_token)
    if not token:
        raise credentials_exception

    if used_cookie and request.method in ("POST", "PUT", "PATCH", "DELETE") and request.url.path != "/auth/token":
        csrf_cookie = request.cookies.get("csrf_token") or ""
        csrf_header = request.headers.get("X-CSRF-Token") or ""
        if not csrf_cookie or not csrf_header or not secrets.compare_digest(csrf_cookie, csrf_header):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token missing or invalid")

    try:
        payload = jwt.decode(token, security.JWT_VERIFYING_KEY, algorithms=[security.ALGORITHM])
        username: str = payload.get("sub")
        jti: str = payload.get("jti")
        if username is None:
            raise credentials_exception
        if jti:
            revoked = db.query(models.TokenBlocklist.id).filter(
                models.TokenBlocklist.jti == jti
            ).first()
            if revoked:
                raise credentials_exception
        token_data = schemas.TokenData(username=username, role=payload.get("role"))
    except JWTError:
        raise credentials_exception
    user = db.query(models.User).filter(models.User.username == token_data.username).first()
    if user is None:
        raise credentials_exception
    return user

async def get_current_active_user(current_user: models.User = Depends(get_current_user)):
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

@router.post("/token", response_model=schemas.Token)
@limiter.limit("5/minute")  # Rate limit: 5 login attempts per minute
async def login_for_access_token(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(), 
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not security.verify_password(form_data.password, user.hashed_password):
        # Log failed attempt
        if user:
            record_audit_log(
                db,
                user_id=user.id,
                action="LOGIN_FAILED",
                details=f"Failed login attempt from IP: {request.state.client_ip}",
                commit=True,
            )
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=security.ACCESS_TOKEN_EXPIRE_MINUTES)
    # Include hierarchy info in token
    token_data = {
        "sub": user.username, 
        "role": user.role.value, # Use value ('sho') for frontend logic
        "rank": user.rank,
        "station": user.station_name,
        "district": user.district_name,
        "zone": user.zone_name
    }
    access_token = security.create_access_token(
        data=token_data, expires_delta=access_token_expires
    )
    
    # Audit Log
    record_audit_log(
        db,
        user_id=user.id,
        action="LOGIN",
        details=f"User logged in successfully from IP: {request.state.client_ip}",
        commit=True,
    )

    _set_auth_cookies(response, access_token)

    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "is_first_login": user.is_first_login
    }

@router.post("/register", response_model=schemas.UserResponse)
def register_user(
    user: schemas.UserCreate, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    # Restrict registration to Admins or designated IT Cell roles
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only localized Admins can register new officers")
    
    db_user = db.query(models.User).filter(models.User.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
        
    db_email = db.query(models.User).filter(models.User.email == user.email).first()
    if db_email:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # FIX: Validate password strength
    is_valid, error_msg = validate_password_strength(user.password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)
    
    hashed_password = security.get_password_hash(user.password)
    db_user = models.User(
        username=user.username,
        email=user.email,
        hashed_password=hashed_password,
        role=user.role,
        rank=user.rank,
        station_name=user.station_name,
        sub_division=user.sub_division,
        district_name=user.district_name,
        range_name=user.range_name,
        zone_name=user.zone_name,
        state_name=user.state_name,
    )
    db.add(db_user)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="Database integrity error. Please check if user already exists.")
    db.refresh(db_user)
    return db_user

@router.get("/me", response_model=schemas.UserResponse)
async def read_users_me(current_user: models.User = Depends(get_current_active_user)):
    return current_user

@router.post("/change-password")
async def change_password(
    data: schemas.PasswordChange,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    if not security.verify_password(data.old_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password incorrect")
    
    # FIX: Validate new password strength
    is_valid, error_msg = validate_password_strength(data.new_password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)
    
    current_user.hashed_password = security.get_password_hash(data.new_password)
    current_user.is_first_login = False
    db.commit()
    
    return {"message": "Password updated successfully"}


@router.post("/refresh", response_model=schemas.Token)
def refresh_access_token(
    request: Request,
    response: Response,
    bearer_token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Rotate the active JWT: revoke the current jti and issue a fresh token."""
    token, _ = _extract_token(request, bearer_token)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    try:
        payload = jwt.decode(token, security.JWT_VERIFYING_KEY, algorithms=[security.ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    old_jti = payload.get("jti")
    exp_ts = payload.get("exp")
    expires_at = datetime.fromtimestamp(exp_ts, tz=timezone.utc) if exp_ts else None

    _prune_expired_blocklist(db)
    if old_jti:
        exists = db.query(models.TokenBlocklist.id).filter(models.TokenBlocklist.jti == old_jti).first()
        if not exists:
            db.add(models.TokenBlocklist(jti=old_jti, expires_at=expires_at))

    access_token_expires = timedelta(minutes=security.ACCESS_TOKEN_EXPIRE_MINUTES)
    token_data = {
        "sub": current_user.username,
        "role": current_user.role.value,
        "rank": current_user.rank,
        "station": current_user.station_name,
        "district": current_user.district_name,
        "zone": current_user.zone_name,
    }
    new_token = security.create_access_token(data=token_data, expires_delta=access_token_expires)
    db.commit()
    _set_auth_cookies(response, new_token)
    return {
        "access_token": new_token,
        "token_type": "bearer",
        "is_first_login": current_user.is_first_login,
    }


@router.post("/logout")
def logout_current_token(
    request: Request,
    response: Response,
    bearer_token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Revoke the active JWT (jti) server-side upon logout and clear auth cookies."""
    token, _ = _extract_token(request, bearer_token)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    try:
        payload = jwt.decode(token, security.JWT_VERIFYING_KEY, algorithms=[security.ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    jti = payload.get("jti")
    exp_ts = payload.get("exp")
    expires_at = datetime.fromtimestamp(exp_ts, tz=timezone.utc) if exp_ts else None

    _prune_expired_blocklist(db)
    if jti:
        exists = db.query(models.TokenBlocklist.id).filter(models.TokenBlocklist.jti == jti).first()
        if not exists:
            db.add(models.TokenBlocklist(jti=jti, expires_at=expires_at))

    record_audit_log(
        db,
        user_id=current_user.id,
        action="LOGOUT",
        details="User logged out and JWT revoked",
    )
    db.commit()
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("csrf_token", path="/")
    return {"message": "Logged out successfully"}
