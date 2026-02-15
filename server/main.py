"""
geminicli2api — Universal Gemini API Proxy Server

FastAPI application providing:
- OpenAI-compatible endpoints (/v1/chat/completions, /v1/models)
- Native Gemini API proxy (/v1beta/*)
- Multi-account Google OAuth with key rotation
"""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from server.gemini_routes import router as gemini_router
from server.openai_routes import router as openai_router
from server.auth import get_credentials, get_user_project_id, onboard_user, set_accounts_manager
from server.accounts_manager import AccountsManager
from server.config import ACCOUNTS_DIR, CREDENTIAL_FILE

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Global AccountsManager instance
accounts_manager = AccountsManager(str(ACCOUNTS_DIR))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown logic."""
    try:
        logging.info("Starting geminicli2api proxy server...")

        # AccountsManager already loaded accounts in __init__
        set_accounts_manager(accounts_manager)

        if accounts_manager.count > 0:
            logging.info(f"Loaded {accounts_manager.count} account(s) from {ACCOUNTS_DIR}")
        else:
            logging.info("No accounts found in accounts/ directory.")

        # Try existing credentials
        env_creds_json = os.getenv("GEMINI_CREDENTIALS")
        creds_file_exists = os.path.exists(CREDENTIAL_FILE)

        if accounts_manager.count > 0 or env_creds_json or creds_file_exists:
            try:
                creds = get_credentials(allow_oauth_flow=False)
                if creds:
                    try:
                        proj_id = get_user_project_id(creds)
                        if proj_id:
                            onboard_user(creds, proj_id)
                            logging.info(f"Successfully onboarded with project ID: {proj_id}")
                        logging.info("Server started successfully with existing credentials.")
                    except Exception as e:
                        logging.error(f"Setup failed: {str(e)}")
                        logging.warning("Server started but may not function properly.")
                else:
                    logging.warning("Could not load credentials. Will authenticate on first request.")
            except Exception as e:
                logging.error(f"Credential loading error: {str(e)}")
        else:
            # No credentials found — run OAuth flow
            logging.info("No credentials found. Starting OAuth authentication flow...")
            try:
                creds = get_credentials(allow_oauth_flow=True)
                if creds:
                    try:
                        proj_id = get_user_project_id(creds)
                        if proj_id:
                            onboard_user(creds, proj_id)
                            logging.info(f"Onboarded with project ID: {proj_id}")
                    except Exception as e:
                        logging.error(f"Setup failed: {str(e)}")
                else:
                    logging.error("Authentication failed. Server will not function until credentials are provided.")
            except Exception as e:
                logging.error(f"Authentication error: {str(e)}")

        from server.config import GEMINI_AUTH_PASSWORD, HOST, PORT
        logging.info(f"Server ready at http://{HOST}:{PORT}")
        logging.info(f"Auth password: {GEMINI_AUTH_PASSWORD}")
        logging.info(f"Accounts loaded: {accounts_manager.count}")

    except Exception as e:
        logging.error(f"Startup error: {str(e)}")

    yield  # app is running

    # Shutdown
    logging.info("Shutting down geminicli2api proxy server...")


app = FastAPI(
    title="geminicli2api",
    description="Universal Gemini API Proxy — OpenAI-compatible + native Gemini endpoints",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.options("/{full_path:path}")
async def handle_preflight(request: Request, full_path: str):
    """Handle CORS preflight requests without authentication."""
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, PATCH, OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Credentials": "true",
        }
    )


@app.get("/")
async def root():
    """Root endpoint — project info. No auth required."""
    return {
        "name": "geminicli2api",
        "description": "Universal Gemini API Proxy — OpenAI-compatible + native Gemini endpoints",
        "version": "2.0.0",
        "accounts": accounts_manager.count,
        "endpoints": {
            "openai_compatible": {
                "chat_completions": "/v1/chat/completions",
                "models": "/v1/models"
            },
            "native_gemini": {
                "models": "/v1beta/models",
                "generate": "/v1beta/models/{model}/generateContent",
                "stream": "/v1beta/models/{model}/streamGenerateContent"
            },
            "health": "/health"
        },
        "authentication": "Required. Use Bearer token, Basic Auth, 'key' query param, or 'x-goog-api-key' header.",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "geminicli2api",
        "accounts": accounts_manager.count,
    }


# Include routers — order matters (openai first, gemini catch-all last)
app.include_router(openai_router)
app.include_router(gemini_router)
