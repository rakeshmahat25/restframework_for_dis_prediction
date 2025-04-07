import json
import logging
import joblib
import os
from django.conf import settings

logger = logging.getLogger(__name__)


def load_json_data(file_path):
    """Load JSON data from a file."""
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading {file_path}: {str(e)}")
        raise


def load_ml_data():
    """Load all ML-related data at startup."""
    try:
        return {
            "symptoms": load_json_data(settings.SYMPTOMS_LIST_PATH),
            "label_encoder": joblib.load(
                os.path.join(settings.ML_DATA_DIR, "label_encoder.pkl")
            ),
            "disease_mapping": load_json_data(
                settings.DISEASE_SPECIALIZATION_MAPPING_PATH
            ),
        }
    except Exception as e:
        logger.critical(f"Failed to load ML resources: {str(e)}")
        raise


def load_ml_model():
    """Load the ML model from disk."""
    try:
        return joblib.load(settings.MODEL_PATH)
    except Exception as e:
        logger.critical(f"Failed to load ML model: {str(e)}")
        raise


# Load data and model once at startup
ML_DATA = load_ml_data()
MODEL = load_ml_model()
