import datetime
import json
import logging
import re
from typing import Any, Self

import requests
from pydantic import BaseModel, EmailStr, field_validator

DEFAULT_API_ENDPOINT = "https://www.scoutnet.se/api"


class ScoutnetMember(BaseModel):
    member_no: int
    first_name: str
    last_name: str
    date_of_birth: datetime.date
    group: str
    contact_mobile_phone: str | None = None
    email: EmailStr | None = None
    contact_alt_email: EmailStr | None = None

    @property
    def display_name(self) -> str:
        return " ".join(filter(None, [self.first_name, self.last_name]))

    @field_validator("contact_mobile_phone")
    @classmethod
    def phone_to_e164(cls, v: Any):
        phone = v
        if isinstance(phone, str) and phone:
            phone = re.sub(r"[\-\s]", "", phone)
            phone = re.sub(r"^0", "+46", phone)
            if re.match(r"^[1-9]", phone):
                phone = f"+{phone}"
            if not re.match(r"^\+\d{11,}$", phone):
                raise ValueError(f"Invalid phone number: {phone}")
        return phone

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, v: Any):
        return v.lower() if isinstance(v, str) else None

    @field_validator("contact_alt_email")
    @classmethod
    def lowercase_contact_alt_email(cls, v: Any):
        return v.lower() if isinstance(v, str) else None

    @classmethod
    def data_validate(cls, data) -> Self:
        return cls.model_validate(
            {k: v.get("value") for k, v in data.items() if "value" in v}
        )


class ScoutnetMailinglistMember(BaseModel):
    member_no: int
    first_name: str
    last_name: str
    email: str | None = None
    extra_emails: list[str]

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, v: Any):
        return v.lower() if isinstance(v, str) else None

    @field_validator("extra_emails")
    @classmethod
    def lowercase_extra_emails(cls, v: Any):
        return [x.lower() for x in v] if isinstance(v, list) else None

    @classmethod
    def data_validate(cls, data) -> Self:
        return cls.model_validate({k: v.get("value") for k, v in data.items()})


class ScoutnetMailinglist(BaseModel):
    id: int
    title: str
    description: str
    aliases: list[str]
    recipients: list[str] | None = None
    members: dict[int, ScoutnetMailinglistMember] | None = None


class ScoutnetClient:
    def __init__(
        self,
        api_id: str,
        api_endpoint: str | None = None,
        api_key_memberlist: str | None = None,
        api_key_customlists: str | None = None,
    ) -> None:
        self.endpoint = api_endpoint or DEFAULT_API_ENDPOINT
        if api_key_memberlist:
            self.session_memberlist = requests.Session()
            self.session_memberlist.auth = (api_id, api_key_memberlist)
        else:
            self.session_memberlist = None
        if api_key_customlists:
            self.session_customlists = requests.Session()
            self.session_customlists.auth = (api_id, api_key_customlists)
        else:
            self.session_customlists = None
        self.logger = logging.getLogger("ScoutnetClient")

    def dump(self, filename: str) -> None:
        """Dump data to file"""
        memberlist_data = self.memberlist()
        customlists_data = self.customlists()

        self.memberlist = lambda: memberlist_data
        self.customlists = lambda: customlists_data

        dump_data = {"memberlist": memberlist_data, "customlists": customlists_data}
        with open(filename, "w") as dump_file:
            json.dump(dump_data, dump_file)

    def restore(self, filename: str) -> None:
        """Restore data from file"""

        with open(filename) as dump_file:
            dump_data = json.load(dump_file)

        memberlist_data = dump_data["memberlist"]
        customlists_data = dump_data["customlists"]

        self.memberlist = lambda: memberlist_data
        self.customlists = lambda: customlists_data

    def memberlist(self) -> Any:
        """Get raw memberlist"""
        url = f"{self.endpoint}/group/memberlist"
        response = self.session_memberlist.get(url)
        response.raise_for_status()
        return response.json()

    def customlists(self) -> Any:
        """Get raw customlists"""
        url = f"{self.endpoint}/group/customlists"
        response = self.session_customlists.get(url)
        response.raise_for_status()
        return response.json()

    def get_list_url(self, list_id: str) -> str:
        return f"{self.endpoint}/group/customlists?list_id={list_id}"

    def get_list(
        self, list_data: dict, fetch_members: bool = True
    ) -> ScoutnetMailinglist:
        url = list_data.get("link")
        # list_id = list_data.get('id')
        # url = self.get_list_url(list_id)
        if url is None:
            raise ValueError("list url not found")
        recipients = set()
        members = {}
        title = list_data.get("title")
        if fetch_members:
            response = self.session_customlists.get(url)
            response.raise_for_status()
            data: dict[str, Any] = response.json().get("data")
            if len(data) > 0:
                for _, member_data in data.items():
                    member = ScoutnetMailinglistMember.data_validate(member_data)
                    self.logger.debug(
                        'Adding member %s (%s %s) to list "%s"',
                        member.email,
                        member.first_name,
                        member.last_name,
                        title,
                    )
                    members[member.member_no] = member
                    if member.email:
                        recipients.add(member.email)
                    if member.extra_emails:
                        for extra_mail in member.extra_emails:
                            recipients.add(extra_mail)
                            self.logger.debug(
                                "Additional address %s for user %s",
                                extra_mail,
                                member.email,
                            )
            recipients = sorted(list(recipients))
        else:
            members = None
            recipients = None
        list_aliases = list_data.get("aliases", {})
        aliases = list(set(list_aliases.values())) if len(list_aliases) > 0 else []
        return ScoutnetMailinglist(
            id=int(list_data["id"]),
            aliases=sorted(aliases),
            members=members,
            recipients=recipients,
            title=title,
            description=list_data.get("description"),
        )

    def get_all_members(self) -> dict[int, ScoutnetMember]:
        """Fetch all members from Scoutnet"""
        res = {
            int(k): ScoutnetMember.data_validate(v)
            for k, v in self.memberlist()["data"].items()
        }
        self.logger.debug("Fetched %d members", len(res))
        return res

    def get_all_lists(
        self,
        limit: int = None,
        fetch_members: bool = True,
        list_ids: set | None = None,
    ) -> dict[int, ScoutnetMailinglist]:
        """Fetch all mailing lists from Scoutnet"""
        all_mlists = {}
        count = 0
        for list_id, list_data in self.customlists().items():
            if list_ids and int(list_id) not in list_ids:
                continue
            count += 1
            mlist = self.get_list(list_data, fetch_members=fetch_members)
            if mlist.members:
                self.logger.debug(
                    "Fetched %s: %s (%d members)",
                    mlist.id,
                    mlist.title,
                    len(mlist.members),
                )
            else:
                self.logger.debug("Fetched %s: %s", mlist.id, mlist.title)
            if len(mlist.aliases) > 0:
                self.logger.debug("Including %s: %s", mlist.id, mlist.title)
                all_mlists[int(list_id)] = mlist
            else:
                self.logger.debug("Excluding %s: %s", mlist.id, mlist.title)
            if limit is not None and count >= limit:
                break
        return all_mlists
