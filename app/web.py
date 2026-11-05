from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _render(request: Request, page: str, **context) -> HTMLResponse:
    settings = request.app.state.settings
    firebase_config = None
    if (
        settings.firebase_project_id
        and settings.firebase_api_key
        and settings.firebase_auth_domain
        and settings.firebase_app_id
    ):
        firebase_config = {
            "apiKey": settings.firebase_api_key,
            "authDomain": settings.firebase_auth_domain,
            "projectId": settings.firebase_project_id,
            "appId": settings.firebase_app_id,
        }
    return templates.TemplateResponse(
        request=request,
        name=f"{page}.html",
        context={
            "firebase_config": firebase_config,
            **context,
        },
    )


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def landing(request: Request):
    return _render(request, "landing", active_nav="home")


@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
def login_page(request: Request):
    return _render(request, "auth", mode="login", active_nav="")


@router.get("/register", response_class=HTMLResponse, include_in_schema=False)
def register_page(request: Request):
    return _render(request, "auth", mode="register", active_nav="")


@router.get("/studio", response_class=HTMLResponse, include_in_schema=False)
def studio(request: Request):
    return _render(request, "studio", active_nav="studio")


@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard(request: Request):
    return _render(request, "dashboard", active_nav="dashboard")


@router.get("/gallery", response_class=HTMLResponse, include_in_schema=False)
def gallery(request: Request):
    return _render(request, "gallery", active_nav="gallery")


@router.get("/billing", response_class=HTMLResponse, include_in_schema=False)
def billing(request: Request):
    return _render(request, "billing", active_nav="plans")
