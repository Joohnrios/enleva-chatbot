from django.apps import AppConfig


class KbConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "cms.kb"
    label = "kb"
    verbose_name = "Base de conhecimento"
