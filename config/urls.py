# корневые маршруты связывают вход, выход и страницы приложения.
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from school.forms import LoginForm
from school.views import logout_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="school/login.html",
            authentication_form=LoginForm,
            redirect_authenticated_user=True,
        ),
        name="login",
    ),
    path("logout/", logout_view, name="logout"),
    path("", include("school.urls")),
]
