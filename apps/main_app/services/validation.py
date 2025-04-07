from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
import os


def check_ml_artifacts():
    """Verify required ML files exist at startup"""
    required_files = [
        settings.MODEL_PATH,
        settings.SYMPTOMS_LIST_PATH,
        settings.DISEASE_SPECIALIZATION_MAPPING_PATH,
        os.path.join(settings.ML_DATA_DIR, "label_encoder.pkl"),
    ]

    missing = [f for f in required_files if not os.path.exists(f)]
    if missing:
        raise ImproperlyConfigured(f"Missing ML artifacts: {', '.join(missing)}")
