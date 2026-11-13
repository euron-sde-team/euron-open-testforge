"""Request and response models for instance settings and self sign-up."""

from __future__ import annotations

from pydantic import Field

from testforge.core.schemas import ApiModel, Email


class PublicSettings(ApiModel):
    """What the sign-in page needs. No secrets."""

    site_name: str
    allow_signup: bool
    # True on a fresh instance: the first sign-up creates the admin and an organization.
    needs_setup: bool = False


class AdminSettings(ApiModel):
    site_name: str
    allow_signup: bool


class SettingsUpdate(ApiModel):
    site_name: str | None = Field(None, min_length=1, max_length=80)
    allow_signup: bool | None = None


class SignupRequest(ApiModel):
    email: Email
    name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=256)
    # The organization created for the new account (default: "<name>'s organization").
    organization: str | None = Field(None, min_length=1, max_length=120)
