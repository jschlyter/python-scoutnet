import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field, field_validator
from pydantic_extra_types.phone_numbers import PhoneNumber

DEFAULT_API_ENDPOINT = "https://www.scoutnet.se/api"

PhoneNumber.default_region_code = "SE"


class ScoutnetBaseModel(BaseModel):
    @classmethod
    def data_validate(cls, data):
        return cls.model_validate(
            {k: v.get("value") for k, v in data.items() if "value" in v}
        )


class ScoutnetMember(ScoutnetBaseModel):
    member_no: int
    first_name: str
    last_name: str
    date_of_birth: datetime.date
    group: str
    contact_mobile_phone: PhoneNumber | None = Field(default=None)
    email: EmailStr | None = None
    contact_alt_email: EmailStr | None = None

    @property
    def display_name(self) -> str:
        return " ".join(filter(None, [self.first_name, self.last_name]))

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, v: Any):
        return v.lower() if isinstance(v, str) else None

    @field_validator("contact_alt_email")
    @classmethod
    def lowercase_contact_alt_email(cls, v: Any):
        return v.lower() if isinstance(v, str) else None


class ScoutnetMailinglistMember(ScoutnetBaseModel):
    member_no: int
    first_name: str
    last_name: str
    email: EmailStr | None = None
    extra_emails: list[EmailStr]

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, v: Any):
        return v.lower() if isinstance(v, str) else None

    @field_validator("extra_emails")
    @classmethod
    def lowercase_extra_emails(cls, v: Any):
        return [x.lower() for x in v] if isinstance(v, list) else None


class ScoutnetMailinglist(BaseModel):
    id: int
    title: str | None
    description: str | None
    aliases: list[str]
    recipients: list[str] | None = None
    members: dict[int, ScoutnetMailinglistMember] | None = None
