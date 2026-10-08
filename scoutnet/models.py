import datetime
from enum import IntEnum, StrEnum
from typing import Any, Self

from pydantic import BaseModel, EmailStr, Field, field_validator
from pydantic_extra_types.phone_numbers import PhoneNumber

PhoneNumber.default_region_code = "SE"
PhoneNumber.phone_format = "E164"


class ScoutnetSex(IntEnum):
    UNKNOWN = 0
    MAN = 1
    WOMAN = 2
    OTHER = 3


class ScoutnetPaymentStatus(StrEnum):
    PAID = "paid"
    NOT_DUE_UNPAID = "not_due_unpaid"
    NOT_INVOICED = "not_invoiced"
    UNPAID_OVERDUE = "unpaid_overdue"
    UNPAID_OVERDUE_REMINDED = "unpaid_overdue_reminded"
    PAID_PARTIAL_CREDIT = "paid_partial_credit"


class ScoutnetBaseModel(BaseModel):
    @classmethod
    def data_validate(cls, data: dict[str, Any]) -> Self:
        properties = {}
        for k, v in data.items():
            value = v.get("value")
            if raw_value := v.get("raw_value"):
                properties[k] = raw_value
                properties[f"{k}_text"] = value
            else:
                properties[k] = value
        return cls.model_validate(properties)


class ScoutnetMember(ScoutnetBaseModel):
    """Model for a Scoutnet member"""

    member_no: int

    first_name: str | None = Field(default=None)
    last_name: str | None = Field(default=None)

    date_of_birth: datetime.date
    ssno: str | None = Field(default=None)
    sex: ScoutnetSex

    email: EmailStr | None = None
    contact_alt_email: EmailStr | None = None

    contact_mobile_phone: PhoneNumber | None = Field(default=None)

    address_1: str | None = Field(default=None)
    address_2: str | None = Field(default=None)
    address_3: str | None = Field(default=None)
    postcode: str | None = Field(default=None)
    town: str | None = Field(default=None)
    country: str | None = Field(default=None)

    group: int
    group_text: str

    unit: int | None = Field(default=None)
    unit_text: str | None = Field(default=None)

    unit_type: int | None = Field(default=None)
    unit_type_text: str | None = Field(default=None)

    patrol: int | None = Field(default=None)
    patrol_text: str | None = Field(default=None)

    created_at: datetime.date
    confirmed_at: datetime.date

    current_term: ScoutnetPaymentStatus | None = Field(default=None)
    current_term_due_date: datetime.date | None = Field(default=None)

    prev_term: ScoutnetPaymentStatus | None = Field(default=None)

    @property
    def display_name(self) -> str | None:
        if self.first_name and self.last_name:
            return " ".join(filter(None, [self.first_name, self.last_name]))
        return None

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, v: Any) -> str | None:
        return v.lower() if isinstance(v, str) else None

    @field_validator("contact_alt_email")
    @classmethod
    def lowercase_contact_alt_email(cls, v: Any) -> str | None:
        return v.lower() if isinstance(v, str) else None


class ScoutnetMailinglistMember(ScoutnetBaseModel):
    """Model for a Scoutnet mailinglist member"""

    member_no: int
    first_name: str
    last_name: str
    email: EmailStr | None = None
    extra_emails: list[EmailStr]

    @property
    def display_name(self) -> str:
        return " ".join(filter(None, [self.first_name, self.last_name]))

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, v: Any) -> str | None:
        return v.lower() if isinstance(v, str) else None

    @field_validator("extra_emails")
    @classmethod
    def lowercase_extra_emails(cls, v: Any) -> list[str] | None:
        return [x.lower() for x in v] if isinstance(v, list) else None


class ScoutnetMailinglist(BaseModel):
    """Model for a Scoutnet mailinglist"""

    id: int
    title: str | None
    description: str | None
    aliases: list[str]
    recipients: list[str] | None = None
    members: list[ScoutnetMailinglistMember] | None = Field(default=None)


class ScoutnetMemberCollection(BaseModel):
    members: list[ScoutnetMember] = Field(default_factory=list)

    def __len__(self) -> int:
        return len(self.members)


class ScoutnetMailinglistCollection(BaseModel):
    lists: list[ScoutnetMailinglist] = Field(default_factory=list)

    def __len__(self) -> int:
        return len(self.lists)
