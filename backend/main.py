from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.staticfiles import StaticFiles
import os

from backend.database import engine, Base
# Import models to creating tables
from backend import models
from backend import config

# Import middleware
from backend.middleware.security import SecurityHeadersMiddleware, RequestLoggingMiddleware

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Police Case Management System")

from backend.routers import auth, cases, requests, files, analysis, admin, evidence, tools
from backend.routers import bank_requests, npci_requests  # Financial Fraud Module
from backend.routers import freeze_requests, financial_analytics  # Phase 4 & 5
from backend.routers import financial_entities  # Entity management

app.include_router(auth.router)
app.include_router(cases.router)
app.include_router(requests.router)
app.include_router(files.router)
app.include_router(analysis.router)
app.include_router(admin.router)
app.include_router(evidence.router)
app.include_router(tools.router) # Cyber Tools
app.include_router(bank_requests.router)  # Bank data requests
app.include_router(npci_requests.router)  # NPCI/UPI requests
app.include_router(freeze_requests.router)  # Account freeze (Section 102)
app.include_router(financial_analytics.router)  # Fraud intelligence
app.include_router(financial_entities.router)  # Financial entity management


# HTTPS Redirect in Production
if config.ENVIRONMENT == "production":
    app.add_middleware(HTTPSRedirectMiddleware)

# Security Headers Middleware
app.add_middleware(SecurityHeadersMiddleware)

# Request Logging Middleware
app.add_middleware(RequestLoggingMiddleware)

# CORS setup - Use environment configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "PUT"],  # Explicit methods only
    allow_headers=["Authorization", "Content-Type", "Accept"],  # Explicit headers only
    expose_headers=["Content-Disposition"],
)

# Mount static files for frontend
app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")


@app.get("/")
def read_root():
    return {"message": "Police CAF/CDR Analysis System API is Online", "environment": config.ENVIRONMENT}

