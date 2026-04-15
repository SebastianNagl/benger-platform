"""
Internationalization (i18n) support for BenGER email verification system
Supports multiple languages for email templates and user interface
"""

from enum import Enum
from typing import Any, Dict, Optional


class SupportedLanguage(Enum):
    """Supported languages for BenGER"""

    ENGLISH = "en"
    GERMAN = "de"


class EmailTranslations:
    """Translation strings for email verification system"""

    translations: Dict[str, Dict[str, Any]] = {
        "en": {
            # Email verification email
            "verification_email": {
                "subject": "Verify your BenGER account",
                "greeting": "Hi {user_name},",
                "welcome_title": "Welcome to BenGER!",
                "intro": "Thank you for registering with BenGER. To complete your registration and access the platform, please verify your email address by clicking the button below:",
                "button_text": "Verify Email Address",
                "expiration_notice": "This link will expire in <strong>48 hours</strong>.",
                "manual_link_text": "If the button doesn't work, you can copy and paste this link into your browser:",
                "important_notice": "<strong>Important:</strong> You must verify your email address before you can log in to BenGER.",
                "ignore_notice": "If you didn't create an account with BenGER, please ignore this email.",
                "footer_description": "BenGER - German Legal Language Model Evaluation Platform",
                "footer_link_text": "Visit BenGER",
            },
            # Reminder email
            "reminder_email": {
                "subject": "Reminder: Verify your BenGER account",
                "greeting": "Hi {user_name},",
                "title": "Email Verification Reminder",
                "intro": "We noticed you haven't verified your email address yet. To access your BenGER account, please verify your email by clicking the button below:",
                "button_text": "Verify Email Address",
                "expiration_notice": "This link will expire in <strong>48 hours</strong>.",
                "manual_link_text": "If the button doesn't work, you can copy and paste this link into your browser:",
                "help_text": "If you're having trouble, please check your spam folder or contact support.",
                "ignore_notice": "If you didn't create an account with BenGER, please ignore this email.",
            },
            # Frontend messages
            "frontend": {
                "verify_email_title": "Verify Your Email",
                "verify_email_instruction": "Please check your email and click the verification link to continue.",
                "verification_required": "Email verification required",
                "verification_required_message": "You must verify your email address before you can log in to BenGER.",
                "didnt_receive_email": "Didn't receive the email?",
                "troubleshooting_tips": [
                    "Check your spam or junk folder",
                    "Make sure you entered the correct email address",
                    "The verification link expires in 48 hours",
                ],
                "resend_verification": "Resend Verification Email",
                "back_to_login": "Back to Login",
                "verification_success": "Email successfully verified! You can now log in.",
                "verification_failed": "Invalid or expired verification link. Please try again.",
                "verification_already_verified": "Your email is already verified.",
            },
            # Invitation-based registration
            "invitation": {
                "signup_with_invitation": "Sign up with invitation",
                "invitation_code": "Invitation code",
                "invitation_code_placeholder": "Enter your invitation code",
                "validate_invitation": "Validate invitation",
                "invitation_valid": "Valid invitation to join {organization_name} as {role}",
                "invitation_invalid": "Invalid or expired invitation code",
                "signup_and_join": "Create account and join organization",
                "invitation_signup_success": "Account created! Check your email to verify and complete registration.",
                "auto_join_message": "After email verification, you'll automatically join {organization_name}.",
                "email_must_match": "Email address must match the invitation ({expected_email})",
                "invitation_expired": "This invitation has expired",
                "invitation_already_used": "This invitation has already been used",
            },
            # Admin interface
            "admin": {
                "email_verification_management": "Email Verification Management",
                "monitor_and_manage": "Monitor and manage email verification system",
                "overview": "Overview",
                "users": "Users",
                "analytics": "Analytics",
                "maintenance": "Maintenance",
                "total_users": "Total Users",
                "verified_users": "Verified Users",
                "unverified_users": "Unverified Users",
                "verification_rate": "Verification Rate",
                "pending_verification": "Pending Verification",
                "expired_tokens": "Expired Tokens",
                "recent_unverified": "Recent Unverified",
                "registered_users": "Registered users",
                "email_verified": "Email verified",
                "need_verification": "Need verification",
                "overall_rate": "Overall rate",
                "awaiting_email_click": "Awaiting email click",
                "need_cleanup": "Need cleanup",
                "last_7_days": "Last 7 days",
                "all_users_verified": "All users have verified their emails!",
                "maintenance_operations": "Maintenance Operations",
                "admin_tasks_description": "Administrative tasks for email verification system",
                "cleanup_expired_tokens": "Cleanup Expired Tokens",
                "cleanup_description": "Remove verification tokens older than 48 hours",
                "send_reminder_emails": "Send Reminder Emails",
                "reminder_description": "Send verification reminders to users without recent emails",
                "refresh_data": "Refresh Data",
                "refresh_description": "Update all statistics and user data",
                "run_cleanup": "Run Cleanup",
                "send_reminders": "Send Reminders",
                "refresh": "Refresh",
            },
        },
        "de": {
            # Email verification email
            "verification_email": {
                "subject": "Verifizieren Sie Ihr BenGER-Konto",
                "greeting": "Hallo {user_name},",
                "welcome_title": "Willkommen bei BenGER!",
                "intro": "Vielen Dank für Ihre Registrierung bei BenGER. Um Ihre Registrierung abzuschließen und auf die Plattform zuzugreifen, bestätigen Sie bitte Ihre E-Mail-Adresse, indem Sie auf die Schaltfläche unten klicken:",
                "button_text": "E-Mail-Adresse verifizieren",
                "expiration_notice": "Dieser Link läuft in <strong>48 Stunden</strong> ab.",
                "manual_link_text": "Falls die Schaltfläche nicht funktioniert, können Sie diesen Link kopieren und in Ihren Browser einfügen:",
                "important_notice": "<strong>Wichtig:</strong> Sie müssen Ihre E-Mail-Adresse verifizieren, bevor Sie sich bei BenGER anmelden können.",
                "ignore_notice": "Falls Sie kein Konto bei BenGER erstellt haben, ignorieren Sie bitte diese E-Mail.",
                "footer_description": "BenGER - Plattform zur Bewertung deutscher Rechtssprach-Modelle",
                "footer_link_text": "BenGER besuchen",
            },
            # Reminder email
            "reminder_email": {
                "subject": "Erinnerung: Verifizieren Sie Ihr BenGER-Konto",
                "greeting": "Hallo {user_name},",
                "title": "Erinnerung zur E-Mail-Verifizierung",
                "intro": "Wir haben bemerkt, dass Sie Ihre E-Mail-Adresse noch nicht verifiziert haben. Um auf Ihr BenGER-Konto zuzugreifen, bestätigen Sie bitte Ihre E-Mail, indem Sie auf die Schaltfläche unten klicken:",
                "button_text": "E-Mail-Adresse verifizieren",
                "expiration_notice": "Dieser Link läuft in <strong>48 Stunden</strong> ab.",
                "manual_link_text": "Falls die Schaltfläche nicht funktioniert, können Sie diesen Link kopieren und in Ihren Browser einfügen:",
                "help_text": "Falls Sie Probleme haben, überprüfen Sie bitte Ihren Spam-Ordner oder kontaktieren Sie den Support.",
                "ignore_notice": "Falls Sie kein Konto bei BenGER erstellt haben, ignorieren Sie bitte diese E-Mail.",
            },
            # Frontend messages
            "frontend": {
                "verify_email_title": "E-Mail verifizieren",
                "verify_email_instruction": "Bitte überprüfen Sie Ihre E-Mails und klicken Sie auf den Verifizierungslink, um fortzufahren.",
                "verification_required": "E-Mail-Verifizierung erforderlich",
                "verification_required_message": "Sie müssen Ihre E-Mail-Adresse verifizieren, bevor Sie sich bei BenGER anmelden können.",
                "didnt_receive_email": "E-Mail nicht erhalten?",
                "troubleshooting_tips": [
                    "Überprüfen Sie Ihren Spam- oder Junk-Ordner",
                    "Stellen Sie sicher, dass Sie die richtige E-Mail-Adresse eingegeben haben",
                    "Der Verifizierungslink läuft in 48 Stunden ab",
                ],
                "resend_verification": "Verifizierungs-E-Mail erneut senden",
                "back_to_login": "Zurück zur Anmeldung",
                "verification_success": "E-Mail erfolgreich verifiziert! Sie können sich jetzt anmelden.",
                "verification_failed": "Ungültiger oder abgelaufener Verifizierungslink. Bitte versuchen Sie es erneut.",
                "verification_already_verified": "Ihre E-Mail ist bereits verifiziert.",
            },
            # Invitation-based registration
            "invitation": {
                "signup_with_invitation": "Mit Einladung registrieren",
                "invitation_code": "Einladungscode",
                "invitation_code_placeholder": "Geben Sie Ihren Einladungscode ein",
                "validate_invitation": "Einladung validieren",
                "invitation_valid": "Gültige Einladung, um {organization_name} als {role} beizutreten",
                "invitation_invalid": "Ungültiger oder abgelaufener Einladungscode",
                "signup_and_join": "Konto erstellen und Organisation beitreten",
                "invitation_signup_success": "Konto erstellt! Überprüfen Sie Ihre E-Mails zur Verifizierung und um die Registrierung abzuschließen.",
                "auto_join_message": "Nach der E-Mail-Verifizierung treten Sie automatisch {organization_name} bei.",
                "email_must_match": "E-Mail-Adresse muss mit der Einladung übereinstimmen ({expected_email})",
                "invitation_expired": "Diese Einladung ist abgelaufen",
                "invitation_already_used": "Diese Einladung wurde bereits verwendet",
            },
            # Admin interface
            "admin": {
                "email_verification_management": "E-Mail-Verifizierung verwalten",
                "monitor_and_manage": "E-Mail-Verifizierungssystem überwachen und verwalten",
                "overview": "Übersicht",
                "users": "Benutzer",
                "analytics": "Analysen",
                "maintenance": "Wartung",
                "total_users": "Benutzer insgesamt",
                "verified_users": "Verifizierte Benutzer",
                "unverified_users": "Unverifizierte Benutzer",
                "verification_rate": "Verifizierungsrate",
                "pending_verification": "Ausstehende Verifizierung",
                "expired_tokens": "Abgelaufene Token",
                "recent_unverified": "Kürzlich unverifiziert",
                "registered_users": "Registrierte Benutzer",
                "email_verified": "E-Mail verifiziert",
                "need_verification": "Benötigen Verifizierung",
                "overall_rate": "Gesamtrate",
                "awaiting_email_click": "Warten auf E-Mail-Klick",
                "need_cleanup": "Benötigen Bereinigung",
                "last_7_days": "Letzte 7 Tage",
                "all_users_verified": "Alle Benutzer haben ihre E-Mails verifiziert!",
                "maintenance_operations": "Wartungsarbeiten",
                "admin_tasks_description": "Administrative Aufgaben für das E-Mail-Verifizierungssystem",
                "cleanup_expired_tokens": "Abgelaufene Token bereinigen",
                "cleanup_description": "Verifizierungs-Token entfernen, die älter als 48 Stunden sind",
                "send_reminder_emails": "Erinnerungs-E-Mails senden",
                "reminder_description": "Verifizierungs-Erinnerungen an Benutzer ohne kürzliche E-Mails senden",
                "refresh_data": "Daten aktualisieren",
                "refresh_description": "Alle Statistiken und Benutzerdaten aktualisieren",
                "run_cleanup": "Bereinigung ausführen",
                "send_reminders": "Erinnerungen senden",
                "refresh": "Aktualisieren",
            },
        },
    }

    @classmethod
    def get(cls, language: str, category: str, key: str, **kwargs) -> str:
        """
        Get translated text with optional formatting

        Args:
            language: Language code (en, de)
            category: Translation category (verification_email, frontend, admin)
            key: Translation key
            **kwargs: Format parameters for string interpolation

        Returns:
            Translated and formatted string
        """
        # Default to English if language not supported
        if language not in cls.translations:
            language = "en"

        # Get translation category
        category_translations = cls.translations[language].get(category, {})

        # Get specific translation
        translation = category_translations.get(key, "")

        # If not found, try English fallback
        if not translation and language != "en":
            category_translations = cls.translations["en"].get(category, {})
            translation = category_translations.get(key, f"[Missing translation: {category}.{key}]")

        # Format with provided arguments
        if kwargs:
            try:
                return translation.format(**kwargs)
            except (KeyError, ValueError):
                return translation

        return translation

    @classmethod
    def get_list(cls, language: str, category: str, key: str) -> list:
        """
        Get translated list (for troubleshooting tips, etc.)

        Args:
            language: Language code
            category: Translation category
            key: Translation key

        Returns:
            List of translated strings
        """
        # Default to English if language not supported
        if language not in cls.translations:
            language = "en"

        # Get translation category
        category_translations = cls.translations[language].get(category, {})

        # Get specific translation
        translation = category_translations.get(key, [])

        # If not found, try English fallback
        if not translation and language != "en":
            category_translations = cls.translations["en"].get(category, {})
            translation = category_translations.get(key, [])

        return translation

    @classmethod
    def detect_user_language(cls, user_agent: str = "", accept_language: str = "") -> str:
        """
        Detect user's preferred language from browser headers

        Args:
            user_agent: User-Agent header
            accept_language: Accept-Language header

        Returns:
            Detected language code (en or de)
        """
        # Check Accept-Language header first
        if accept_language:
            # Parse Accept-Language header (e.g., "de-DE,de;q=0.9,en;q=0.8")
            for lang_item in accept_language.split(","):
                lang = lang_item.split(";")[0].strip().lower()
                if lang.startswith("de"):
                    return "de"
                elif lang.startswith("en"):
                    return "en"

        # Default to English
        return "en"


class LanguageDetector:
    """Utility class for detecting user language preferences"""

    @staticmethod
    def detect_from_request_headers(user_agent: str = "", accept_language: str = "") -> str:
        """Detect language from HTTP request headers"""
        return EmailTranslations.detect_user_language(user_agent, accept_language)

    @staticmethod
    def detect_from_user_profile(user_locale: Optional[str] = None) -> str:
        """Detect language from user profile settings"""
        if user_locale:
            if user_locale.startswith("de"):
                return "de"
            elif user_locale.startswith("en"):
                return "en"
        return "en"


# Convenience functions for easy access
def t(language: str, category: str, key: str, **kwargs) -> str:
    """Shorthand for EmailTranslations.get()"""
    return EmailTranslations.get(language, category, key, **kwargs)


def t_list(language: str, category: str, key: str) -> list:
    """Shorthand for EmailTranslations.get_list()"""
    return EmailTranslations.get_list(language, category, key)
