# конфигурация приложения школы для django.
from django.apps import AppConfig


class SchoolConfig(AppConfig):
    # задаёт имя приложения и тип ключа его моделей.
    default_auto_field = "django.db.models.BigAutoField"
    name = "school"
