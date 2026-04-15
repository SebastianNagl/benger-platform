"""
Localization package for BenGER
Provides internationalization support for email verification system
"""

from .translations import EmailTranslations, LanguageDetector, SupportedLanguage, t, t_list

__all__ = ["EmailTranslations", "LanguageDetector", "SupportedLanguage", "t", "t_list"]
