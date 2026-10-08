import asyncio
import json
import logging
import time
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

        self.httpx2_client = httpx2.AsyncClient(http2=True)

        self.memberlist_auth = (
            (str(api_id), api_key_memberlist) if api_key_memberlist else None
        )
        self.customlists_auth = (
            (str(api_id), api_key_customlists) if api_key_customlists else None
        )

    async def dump(self, filename: str) -> None:
        """Dump data to file"""

        memberlist_data = await self._get_raw_memberlist()
        customlists_data = await self._get_raw_customlists()

        dump_data = {"memberlist": memberlist_data, "customlists": customlists_data}
        with open(filename, "w") as dump_file:
            json.dump(dump_data, dump_file)

    async def restore(self, filename: str) -> None:
        """Restore data from file"""

        with open(filename) as dump_file:
            dump_data = json.load(dump_file)

        self.memberlist_data = dump_data["memberlist"]
        self.customlists_data = dump_data["customlists"]

    def reset(self) -> None:
        """Reset cached data"""
        self.memberlist_data = None
        self.customlists_data = None

    async def _get_raw_memberlist(self, force: bool = False) -> Any:
        """Get raw memberlist"""

        if self.memberlist_data is None or force:
            if not self.memberlist_auth:
                raise RuntimeError("No API key for memberlist")
            url = f"{self.endpoint}/group/memberlist"
            response = await self.httpx2_client.get(url, auth=self.memberlist_auth)
            response.raise_for_status()
            self.memberlist_data = response.json()

        return self.memberlist_data

    async def _get_raw_customlists(self, force: bool = False) -> Any:
        """Get raw customlists"""

        if self.customlists_data is None or force:
            if not self.customlists_auth:
                raise RuntimeError("No API key for customlists")
            url = f"{self.endpoint}/group/customlists"
            response = await self.httpx2_client.get(url, auth=self.customlists_auth)
            response.raise_for_status()
            self.customlists_data = response.json()

        return self.customlists_data

    async def get_list(
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
            if not self.customlists_auth:
                raise RuntimeError("No API key for customlists")
            response = await self.httpx2_client.get(url, auth=self.customlists_auth)
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
            title=title,
            description=list_data.get("description"),
            aliases=sorted(aliases),
            recipients=recipients,
            members=members,
        )

    async def get_all_members(
        self,
        force: bool = False,
    ) -> ScoutnetMemberCollection:
        """Fetch all members from Scoutnet"""

        res = [
            ScoutnetMember.data_validate(v)
            for v in (await self._get_raw_memberlist(force=force))["data"].values()
        ]

        self.logger.debug("Fetched %d members", len(res))

        return ScoutnetMemberCollection(members=res)

    async def get_all_lists(
        self,
        limit: int | None = None,
        fetch_members: bool = True,
        list_ids: set[int] | None = None,
        force: bool = False,
        max_tasks: int = 10,
    ) -> ScoutnetMailinglistCollection:
        """Fetch all mailing lists from Scoutnet, using up to max_tasks concurrent tasks"""

        selected = [
            list_data
            for list_id, list_data in (
                await self._get_raw_customlists(force=force)
            ).items()
            if not list_ids or int(list_id) in list_ids
        ]
        if limit is not None:
            selected = selected[:limit]

        semaphore = asyncio.Semaphore(max_tasks)

        async def fetch(list_data: Any) -> ScoutnetMailinglist:
            async with semaphore:
                self.logger.debug(
                    "Fetching list %s: %s",
                    list_data["id"],
                    list_data.get("title"),
                )
                t1 = time.perf_counter()
                mlist = await self.get_list(list_data, fetch_members=fetch_members)
                t2 = time.perf_counter()
            if mlist.members:
                self.logger.debug(
                    "Fetched %s: %s (%d members) in %.2f seconds",
                    mlist.id,
                    mlist.title,
                    len(mlist.members),
                    t2 - t1,
                )
            else:
                self.logger.debug("Fetched %s: %s", mlist.id, mlist.title)
            return mlist

        res = []
        for mlist in await asyncio.gather(*(fetch(d) for d in selected)):
            if len(mlist.aliases) > 0:
                self.logger.debug("Including %s: %s", mlist.id, mlist.title)
                res.append(mlist)
            else:
                self.logger.debug("Excluding %s: %s", mlist.id, mlist.title)

        return ScoutnetMailinglistCollection(lists=res)
