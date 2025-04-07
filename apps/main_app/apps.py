from django.apps import AppConfig

# from django.conf import settings


class MainAppConfig(AppConfig):
    name = "apps.main_app"

    def ready(self):
        # Connect signals
        from . import signals
        from .services.validation import check_ml_artifacts

        check_ml_artifacts()
