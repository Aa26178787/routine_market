from django.conf import settings
from django.utils.deprecation import MiddlewareMixin


class AdminSessionIsolationMiddleware(MiddlewareMixin):
    """Map admin requests to a separate, path-scoped session cookie."""

    def process_request(self, request):
        request._uses_admin_session_cookie = request.path_info.startswith(
            settings.ADMIN_SESSION_COOKIE_PATH
        )
        if not request._uses_admin_session_cookie:
            return

        admin_session_key = request.COOKIES.get(settings.ADMIN_SESSION_COOKIE_NAME)
        if admin_session_key:
            request.COOKIES[settings.SESSION_COOKIE_NAME] = admin_session_key
        else:
            request.COOKIES.pop(settings.SESSION_COOKIE_NAME, None)

    def process_response(self, request, response):
        if not getattr(request, "_uses_admin_session_cookie", False):
            return response

        session_cookie = response.cookies.get(settings.SESSION_COOKIE_NAME)
        if session_cookie is None:
            return response

        response.cookies[settings.ADMIN_SESSION_COOKIE_NAME] = session_cookie.value
        admin_cookie = response.cookies[settings.ADMIN_SESSION_COOKIE_NAME]
        for attribute in session_cookie.keys():
            if session_cookie[attribute]:
                admin_cookie[attribute] = session_cookie[attribute]
        admin_cookie["path"] = settings.ADMIN_SESSION_COOKIE_PATH
        del response.cookies[settings.SESSION_COOKIE_NAME]
        return response
