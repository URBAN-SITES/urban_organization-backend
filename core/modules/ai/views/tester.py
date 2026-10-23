from pathlib import Path

from django.http import HttpResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET


@require_GET
@ensure_csrf_cookie
def analysis_tester(request):
    page = Path(__file__).resolve().parents[1] / "analyze.html"
    return HttpResponse(page.read_bytes(), content_type="text/html; charset=utf-8")
