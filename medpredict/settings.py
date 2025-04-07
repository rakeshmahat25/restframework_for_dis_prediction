import os
from pathlib import Path
from datetime import timedelta

# import json

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# ML Data Configuration
ML_DATA_DIR = os.path.join(BASE_DIR, "ml_models")
SYMPTOMS_LIST_PATH = os.path.join(ML_DATA_DIR, "master_symptoms.json")
DISEASES_LIST_PATH = os.path.join(ML_DATA_DIR, "diseases.json")
DISEASE_SPECIALIZATION_MAPPING_PATH = os.path.join(
    ML_DATA_DIR, "disease_specialization_mapping.json"
)
MODEL_PATH = os.path.join(ML_DATA_DIR, "trained_model.pkl")


# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "django-insecure-*s=!%jcl8kowop84hn^jx8#qv2@ooscx2&y-!p=1*zfz0=@@r9"


DEBUG = True  # Set to False to enable email sending

ALLOWED_HOSTS = ["*"]  # Update with specific domains in production

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    'django_filters',
    "rest_framework_simplejwt",
    "corsheaders",
    "channels",
    # Project-specific apps
    "apps.accounts",
    "apps.chats",
    "apps.main_app",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # "main_app.middleware.CustomExceptionHandler",
]

ROOT_URLCONF = "medpredict.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "medpredict.wsgi.application"

ASGI_APPLICATION = "medpredict.asgi.application"


CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}


# For production (requires redis-server running):
# CHANNEL_LAYERS = {
#     "default": {
#         "BACKEND": "channels.layers.InMemoryChannelLayer",
#         "CONFIG": {
#             "hosts": [("127.0.0.1", 6379)],
#         },
#     },
# }

TIME_ZONE = "UTC"
USE_TZ = True



# DATABASES = {
#     "default": {
#         "ENGINE": "django.db.backends.postgresql",
#         "NAME": os.getenv("PGDATABASE", "medpredict_db"),
#         "USER": os.getenv("PGUSER", "myuser"),
#         "PASSWORD": os.getenv("PGPASSWORD", "mypassword"),
#         "HOST": os.getenv("PGHOST", "127.0.0.1"),
#         "PORT": os.getenv("PGPORT", "5433"),
#         "ATOMIC_REQUESTS": True,
#     }
# }

DATABASES = {
      'default': {
          'ENGINE': 'django.db.backends.postgresql',
          'NAME': 'medpredict_db', 
          'USER': 'postgres',  
          'PASSWORD': 'postgre@123',  
          'HOST': '127.0.0.1',  
          'PORT': '5432',  
      }
  }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static and media files
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "static"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Custom user model
AUTH_USER_MODEL = "accounts.User"

# CORS settings
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",  # Adjust for frontend origin
]

# REST framework settings
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication', #Optional
        'rest_framework.authentication.BasicAuthentication' #Optional
    ],
    # "DEFAULT_RENDERER_CLASSES": [
    #     "nothing_for_now.renderers.CustomRenderer",
    #     "rest_framework.renderers.BrowsableAPIRenderer",
    # ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 10,
    "DEFAULT_THROTTLE_RATES": {
        "feedback": "20/hour",
        "chats": "100/hour",
    },
}


# Simple JWT configuration
# SIMPLE_JWT = {
#     "ACCESS_TOKEN_LIFETIME": timedelta(days=50),
#     "REFRESH_TOKEN_LIFETIME": timedelta(days=100),
#     "AUTH_HEADER_TYPES": ("Bearer",),
#     "USER_ID_FIELD": "id",
#     "USER_ID_CLAIM": "user_id",
#     "TOKEN_OBTAIN_SERIALIZER": "rest_framework_simplejwt.serializers.TokenObtainPairSerializer",
# }

from datetime import timedelta

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60), # e.g., 1 hour
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
    'ROTATE_REFRESH_TOKENS': False, # Set to True if you want a new refresh token on refresh
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True, # Update user's last_login field upon login

    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY, # Uses Django's SECRET_KEY by default
    'VERIFYING_KEY': None,
    'AUDIENCE': None,
    'ISSUER': None,
    'JWK_URL': None,
    'LEEWAY': 0,

    'AUTH_HEADER_TYPES': ('Bearer',), # Expect 'Authorization: Bearer <token>'
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'USER_AUTHENTICATION_RULE': 'rest_framework_simplejwt.authentication.default_user_authentication_rule',

    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
    'TOKEN_USER_CLASS': 'rest_framework_simplejwt.models.TokenUser',

    'JTI_CLAIM': 'jti',

    'SLIDING_TOKEN_REFRESH_EXP_CLAIM': 'refresh_exp',
    'SLIDING_TOKEN_LIFETIME': timedelta(minutes=5), # Not used if ROTATE_REFRESH_TOKENS is False
    'SLIDING_TOKEN_REFRESH_LIFETIME': timedelta(days=1), # Not used if ROTATE_REFRESH_TOKENS is False

    'TOKEN_OBTAIN_SERIALIZER': 'accounts.serializers.MyTokenObtainPairSerializer',
}

# Email configuration
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = ""
EMAIL_HOST_PASSWORD = ""

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# OTP settings
VALIDATE_OTP = True
OTP_VALID_DURATION = 1 * 60 * 60  # 1 hour in seconds
OTP_LENGTH = 4
ALLOW_NULL_VALUES_IN_RESPONSE = False

USERNAME_FIELD = "email"
