from django.conf import settings
from django.utils.timezone import now
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import JSONParser, MultiPartParser
from django.contrib.auth.password_validation import validate_password
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from .models import User, OTP
from .serializers import (
    LoginSerializer,
    SignupSerializer,
    OTPVerificationSerializer,
    UserProfileSerializer,
    UserListSerializer,
    UserUpdateSerializer,
)
from adapters import Email
from .permissions import IsOTPVerified

import logging

logger = logging.getLogger(__name__)


# Helper function to generate JWT tokens
def get_tokens(user):
    refresh = RefreshToken.for_user(user)
    refresh["user_type"] = user.user_type  # Add custom claim
    return {"refresh": str(refresh), "access": str(refresh.access_token)}


# Helper function to prepare the response
def get_response(user_res, tokens):
    return {
        **user_res,  # Preserves id, otp_verified, email
        "token": tokens["access"],
        "refresh_token": tokens["refresh"],
    }


class AuthViewSet(viewsets.ViewSet):
    """
    ViewSet for handling authentication-related actions: signup, login, OTP generation, and validation.
    """

    permission_classes = [AllowAny]

    @action(detail=False, methods=["post"], url_path="signup")
    def signup(self, request):
        try:
            logger.info(f"Signup request data: {request.data}")
            serializer = SignupSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            user = serializer.save()
            return Response(
                {
                    "message": "User registered successfully. Please verify your email with the OTP sent.",
                    "user_id": str(user.id),
                },
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            logger.error(f"Signup error: {str(e)}", exc_info=True)
            return Response(
                {"detail": "An error occurred during signup. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


    @action(detail=False, methods=["post"], url_path="login")
    def login(self, request):
        try:
            print("Login attempt with data:", request.data)
            
            serializer = LoginSerializer(data=request.data)
            
            if not serializer.is_valid():
                print(f"Serializer validation failed with errors: {serializer.errors}")
                return Response(
                    {"detail": "Invalid email or password"},
                    status=status.HTTP_401_UNAUTHORIZED
                )
                
            user = serializer.validated_data["user"]
            print(f"User authenticated: {user.email}")

            if not user.otp_verified:
                logger.warning(f"User {user.email} attempted login without OTP verification")
                return Response(
                    {"detail": "Please verify your account via OTP first."},
                    status=status.HTTP_403_FORBIDDEN
                )

            # Update login stats
            user.login_count += 1
            user.last_login = now()
            user.save()

            # Generate tokens
            tokens = get_tokens(user)
            login_res = get_response(user.get_login_response(), tokens)
            logger.info(f"Successful login for user {user.email}")
            return Response(login_res, status=status.HTTP_200_OK)

        except AuthenticationFailed as e:
            logger.warning(f"Authentication failed: {str(e)}")
            return Response(
                {"detail": str(e)},
                status=status.HTTP_401_UNAUTHORIZED
            )

    @action(detail=False, methods=["post"], url_path="validate-otp")
    def validate_otp(self, request):
        try:
            print("Received OTP validation request:", request.data)  # Debugging
            serializer = OTPVerificationSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            email = serializer.validated_data["email"]
            otp = serializer.validated_data["otp"]

            print(f"Validating OTP for email: {email}, OTP: {otp}")  # Debugging

            user = User.objects.filter(email=email).first()
            if not user:
                print("User not found")  # Debugging
                return Response(
                    {"detail": "User with this email does not exist."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Finding the OTP without filtering by is_used=False
            otp_instance = OTP.objects.filter(user=user, otp=otp).first()
            if not otp_instance:
                print("Invalid or expired OTP")  # Debugging
                return Response(
                    {"detail": "Invalid or expired OTP."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if otp_instance.is_expired or otp_instance.is_used:
                print("OTP is expired or already used")  # Debugging
                return Response(
                    {"detail": "Invalid or expired OTP."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Only handle Registration OTPs
            if otp_instance.otp_type != "Registration":
                return Response(
                    {"detail": "Invalid OTP type for this endpoint."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Mark OTP as used and verify user
            otp_instance.is_used = True
            otp_instance.save()
            user.otp_verified = True
            user.is_active = True
            user.save()
            tokens = get_tokens(user)
            login_res = get_response(user.get_login_response(), tokens)
            return Response(login_res, status=status.HTTP_200_OK)

        except Exception as e:
            print(f"Error in validate_otp: {str(e)}")  # Debugging
            return Response(
                {"detail": "Internal server error."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=["post"], url_path="request-password-reset")
    def request_password_reset(self, request):
        email = request.data.get("email")
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            logger.error(f"User with email {email} not found.")
            return Response(
                {"detail": "User does not exist."}, status=status.HTTP_400_BAD_REQUEST
            )

        otp = OTP.create(user.id, "Password Reset")
        logger.info(f"OTP created: {otp.otp}, OTP ID: {otp.id}, User ID: {user.id}")

        if not settings.DEBUG:
            mail = Email()
            mail_data = {
                "subject": "Password Reset OTP",
                "message": f"Your OTP is {otp.otp}. Please use it to verify your password reset.",
                "to": [user.email],
            }
            mail.send(mail_data)
        return Response(
            {"message": "OTP has been sent to your email."}, status=status.HTTP_200_OK
        )

    @action(detail=False, methods=["post"], url_path="reset-password")
    def reset_password(self, request):
        email = request.data.get("email")
        otp_code = request.data.get("otp")
        password = request.data.get("password")

        # Get user by email
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            logger.error(f"User with email {email} not found.")
            return Response(
                {"detail": "Invalid user."}, status=status.HTTP_400_BAD_REQUEST
            )

        # Find the valid OTP for the user
        otp_instance = OTP.objects.filter(
            user=user, otp=otp_code, otp_type="Password Reset", is_used=False
        ).first()

        if not otp_instance:
            logger.error(f"No valid OTP found for user {user.id}.")
            return Response(
                {"detail": "Invalid or expired OTP."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if otp_instance.is_expired:
            logger.error(f"OTP expired for user {user.id}.")
            return Response(
                {"detail": "Invalid or expired OTP."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate password
        try:
            validate_password(password, user)
        except Exception as e:
            logger.error(f"Password validation failed: {e}")
            return Response({"detail": e.messages}, status=status.HTTP_400_BAD_REQUEST)

        # Reset password
        user.set_password(password)
        user.save()

        # Mark OTP as used
        otp_instance.is_used = True
        otp_instance.save()

        # Send confirmation email
        if not settings.DEBUG:
            mail_data = {
                "subject": "Password Reset Success",
                "message": "Your password was successfully reset.",
                "to": [user.email],
            }
            try:
                mail = Email()
                mail.send(mail_data)
            except Exception as e:
                logger.error(f"Failed to send email: {e}")
                return Response(
                    {"detail": "Failed to send email."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        # Return tokens
        tokens = get_tokens(user)
        login_res = get_response(user.get_login_response(), tokens)
        return Response(login_res, status=status.HTTP_200_OK)


class UserViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing user profiles.
    """

    queryset = User.objects.all()
    serializer_class = UserProfileSerializer
    lookup_field = "id"
    parser_classes = [JSONParser, MultiPartParser]
    permission_classes = [IsAuthenticated, IsOTPVerified]

    def get_serializer_class(self):
        if self.action == "list":
            return UserListSerializer
        if self.action in ["me", "profile"]:
            return UserProfileSerializer
        if self.action == "partial_update":
            return UserUpdateSerializer
        return super().get_serializer_class()

    @action(detail=False, methods=["get"], url_path="me")
    def me(self, request):
        serializer = self.get_serializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="profile")
    def profile(self, request):
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["patch"], url_path="update-profile")
    def update_profile(self, request):
        user = request.user
        serializer = UserUpdateSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        # Return the full user profile using UserProfileSerializer
        updated_user = User.objects.get(id=user.id)
        profile_serializer = UserProfileSerializer(updated_user)
        return Response(profile_serializer.data, status=status.HTTP_200_OK)
