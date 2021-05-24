import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

import requests

DEFAULT_API_ENDPOINT = "https://www.scoutnet.se/api"


@dataclass(frozen=True)
class ScoutnetMember:
    member_no: int
    first_name: Optional[str]
    last_name: Optional[str]
    contact_mobile_phone: Optional[str]

    def __repr__(self):
        return ", ".join(
            [
                str(self.member_no),
                self.first_name,
                self.last_name,
                self.contact_mobile_phone or "",
            ]
        )

    @staticmethod
    def phone_to_e164(phone: Optional[str]) -> Optional[str]:
        if phone:
            phone = re.sub(r"[\-\s]", "", phone)
            phone = re.sub(r"^0", "+46", phone)
            if re.match(r"^[1-9]", phone):
                phone = f"+{phone}"
            if not re.match(r"^\+\d{11,}$", phone):
                logging.warning("Invalid phone number: %s", phone)
                return None
        return phone

    @staticmethod
    def get_data(field: str, data: dict):
        if field in data:
            return data[field]["value"]

    @classmethod
    def from_data(cls, data):
        return cls(
            member_no=int(cls.get_data("member_no", data)),
            first_name=cls.get_data("first_name", data),
            last_name=cls.get_data("last_name", data),
            contact_mobile_phone=cls.phone_to_e164(
                cls.get_data("contact_mobile_phone", data)
            ),
        )


@dataclass(frozen=True)
class ScoutnetMailinglistMember:
    member_no: int
    first_name: Optional[str]
    last_name: Optional[str]
    email: Optional[str]
    extra_emails: List[str] = field(default_factory=list)

    @staticmethod
    def get_data(field: str, data: dict):
        if field in data:
            return data[field]["value"]

    @classmethod
    def from_data(cls, data):
        if "email" in data:
            email = cls.get_data("email", data).lower()
        else:
            email = None
        return cls(
            member_no=int(cls.get_data("member_no", data)),
            first_name=cls.get_data("first_name", data),
            last_name=cls.get_data("last_name", data),
            email=email,
            extra_emails=[x.lower() for x in data["extra_emails"]["value"]],
        )


@dataclass(frozen=True)
class ScoutnetMailinglist:
    id: int
    title: str
    description: str
    aliases: List[str]
    recipients: Optional[List[str]] = None
    members: Optional[Dict[int, ScoutnetMailinglistMember]] = None


class ScoutnetClient(object):
    def __init__(
        self,
        api_id: str,
        api_endpoint: Optional[str] = None,
        api_key_memberlist: Optional[str] = None,
        api_key_customlists: Optional[str] = None,
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

    def dump(self, filename: str):
        """Dump data to file"""
        memberlist_data = client.memberlist()
        customlists_data = client.customlists()

        client.memberlist = lambda: memberlist_data
        client.customlists = lambda: customlists_data

        dump_data = {"memberlist": memberlist_data, "customlists": customlists_data}
        with open(filename, "wt") as dump_file:
            json.dump(dump_data, dump_file)

    def restore(self, filename: str):
        """Restore data from file"""

        with open(filename, "rt") as dump_file:
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
            data: Dict[str, Any] = response.json().get("data")
            if len(data) > 0:
                for (_, member_data) in data.items():
                    member = ScoutnetMailinglistMember.from_data(member_data)
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
        if len(list_aliases) > 0:
            aliases = list(set(list_aliases.values()))
        else:
            aliases = []
        return ScoutnetMailinglist(
            id=int(list_data["id"]),
            aliases=sorted(aliases),
            members=members,
            recipients=recipients,
            title=title,
            description=list_data.get("description"),
        )

    def get_all_members(self) -> Dict[int, ScoutnetMember]:
        """Fetch all members from Scoutnet"""
        res = {
            int(k): ScoutnetMember.from_data(v)
            for k, v in self.memberlist()["data"].items()
        }
        self.logger.info("Fetched %d members", len(res))
        return res

    def get_all_lists(
        self,
        limit: int = None,
        fetch_members: bool = True,
        list_ids: Optional[Set] = None,
    ) -> Dict[int, ScoutnetMailinglist]:
        """Fetch all mailing lists from Scoutnet"""
        all_mlists = {}
        count = 0
        for (list_id, list_data) in self.customlists().items():
            if list_ids and int(list_id) not in list_ids:
                continue
            count += 1
            mlist = self.get_list(list_data, fetch_members=fetch_members)
            if mlist.members:
                self.logger.info(
                    "Fetched %s: %s (%d members)",
                    mlist.id,
                    mlist.title,
                    len(mlist.members),
                )
            else:
                self.logger.info("Fetched %s: %s", mlist.id, mlist.title)
            if len(mlist.aliases) > 0:
                self.logger.debug("Including %s: %s", mlist.id, mlist.title)
                all_mlists[int(list_id)] = mlist
            else:
                self.logger.debug("Excluding %s: %s", mlist.id, mlist.title)
            if limit is not None and count >= limit:
                break
        return all_mlists
