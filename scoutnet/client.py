import json
import logging
from typing import Any

import httpx2

from .models import (
    ScoutnetMailinglist,
    ScoutnetMailinglistCollection,
    ScoutnetMailinglistMember,
    ScoutnetMember,
    ScoutnetMemberCollection,
)

DEFAULT_API_ENDPOINT = "https://www.scoutnet.se/api"


class ScoutnetClient:
    def __init__(
        self,
        api_id: str | int,
        api_endpoint: str | None = None,
        api_key_memberlist: str | None = None,
        api_key_customlists: str | None = None,
    ) -> None:
        self.logger = logging.getLogger(__name__).getChild(self.__class__.__name__)
        self.endpoint = api_endpoint or DEFAULT_API_ENDPOINT

        self.memberlist_data = None
        self.customlists_data = None

        if api_key_memberlist:
            self.httpx2_client_memberlist = httpx2.Client(http2=True)
            self.httpx2_client_memberlist.auth = (str(api_id), api_key_memberlist)
        else:
            self.httpx2_client_memberlist = None

        if api_key_customlists:
            self.httpx2_client_customlists = httpx2.Client(http2=True)
            self.httpx2_client_customlists.auth = (str(api_id), api_key_customlists)
        else:
            self.httpx2_client_customlists = None

    def dump(self, filename: str) -> None:
        """Dump data to file"""

        memberlist_data = self._get_raw_memberlist()
        customlists_data = self._get_raw_customlists()

        dump_data = {"memberlist": memberlist_data, "customlists": customlists_data}
        with open(filename, "w") as dump_file:
            json.dump(dump_data, dump_file)

    def restore(self, filename: str) -> None:
        """Restore data from file"""

        with open(filename) as dump_file:
            dump_data = json.load(dump_file)

        self.memberlist_data = dump_data["memberlist"]
        self.customlists_data = dump_data["customlists"]

    def reset(self) -> None:
        """Reset cached data"""
        self.memberlist_data = None
        self.customlists_data = None

    def _get_raw_memberlist(self, force: bool = False) -> Any:
        """Get raw memberlist"""

        if self.memberlist_data is None or force:
            if not self.httpx2_client_memberlist:
                raise RuntimeError("No API key for memberlist")
            url = f"{self.endpoint}/group/memberlist"
            response = self.httpx2_client_memberlist.get(url)
            response.raise_for_status()
            self.memberlist_data = response.json()

        return self.memberlist_data

    def _get_raw_customlists(self, force: bool = False) -> Any:
        """Get raw customlists"""

        if self.customlists_data is None or force:
            if not self.httpx2_client_customlists:
                raise RuntimeError("No API key for customlists")
            url = f"{self.endpoint}/group/customlists"
            response = self.httpx2_client_customlists.get(url)
            response.raise_for_status()
            self.customlists_data = response.json()

        return self.customlists_data

    def get_list_url(self, list_id: str) -> str:
        return f"{self.endpoint}/group/customlists?list_id={list_id}"

    def get_list(
        self, list_data: dict, fetch_members: bool = True
    ) -> ScoutnetMailinglist:
        """Get mailinglist"""

        url = list_data.get("link")
        if url is None:
            raise ValueError("list url not found")

        recipients = set()
        members: list[ScoutnetMailinglistMember] | None = []
        title = list_data.get("title")

        if fetch_members:
            if not self.httpx2_client_customlists:
                raise RuntimeError("No API key for customlists")
            response = self.httpx2_client_customlists.get(url)
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
                    members.append(member)
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

    def get_all_members(
        self,
        force: bool = False,
    ) -> ScoutnetMemberCollection:
        """Fetch all members from Scoutnet"""

        res = [
            ScoutnetMember.data_validate(v)
            for v in self._get_raw_memberlist(force=force)["data"].values()
        ]

        self.logger.debug("Fetched %d members", len(res))

        return ScoutnetMemberCollection(members=res)

    def get_all_lists(
        self,
        limit: int | None = None,
        fetch_members: bool = True,
        list_ids: set[int] | None = None,
        force: bool = False,
    ) -> ScoutnetMailinglistCollection:
        """Fetch all mailing lists from Scoutnet"""

        res = []
        count = 0

        for list_id, list_data in self._get_raw_customlists(force=force).items():
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
                res.append(mlist)
            else:
                self.logger.debug("Excluding %s: %s", mlist.id, mlist.title)
            if limit is not None and count >= limit:
                break

        return ScoutnetMailinglistCollection(lists=res)
