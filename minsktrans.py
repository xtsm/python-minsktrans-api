import ssl
import re
import sys
import time
import enum
import asyncio

import aiohttp
import bs4


class Place(enum.Enum):
    Minsk = "minsk"
    Region = "region"


class TransportType(enum.Enum):
    Bus = "bus"
    Trolleybus = "trolleybus"
    Tram = "tram"


class RetardProtectionOp(enum.Enum):
    Xor = "^"
    Add = "+"


class RateLimiter:
    def __init__(self, rps):
        self._period = 1 / rps
        self._allowed = 0

    async def __aenter__(self):
        now = time.time()
        allowed = self._allowed
        self._allowed = max(now, allowed) + self._period
        if now < allowed:
            await asyncio.sleep(allowed - now)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class RetardProtection:
    def __init__(self, num, op):
        self._num = num
        self._op = op

    def __call__(self, value):
        if isinstance(value, str):
            t = 0
            for c in value:
                if not c.isdigit():
                    break
                t = t * 10 + int(c)
            value = t
        if self._op == RetardProtectionOp.Xor:
            return self._num ^ value
        elif self._op == RetardProtectionOp.Add:
            return self._num + value
        else:
            raise RuntimeError(self._op)


class MinsktransClient:
    FRONT_URL = "https://www.minsktrans.by/lookout_yard/Home/Index/minsk"
    RPS = 3
    RETARD_PROTECTION_RE = re.compile(r"'v': function \(a\) { return (\d+) (.) a; }")

    async def __aenter__(self):
        if hasattr(self, "_session"):
            raise RuntimeError("session already opened")
        # their certs are fucked up
        self._ssl = ssl.create_default_context()
        self._ssl.check_hostname = False
        self._ssl.verify_mode = ssl.CERT_NONE

        self._session = await aiohttp.ClientSession().__aenter__()
        self._rl = RateLimiter(self.RPS)
        try:
            self._token, self._rp = await self._retrieve_token_and_retard_protection()
        except:
            await self._session.__aexit__(*sys.exc_info())
            del self._session
            raise
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._session.__aexit__(exc_type, exc_val, exc_tb)
        del self._session, self._token, self._rp, self._ssl, self._rl

    async def _retrieve_token_and_retard_protection(self):
        async with self._session.get(self.FRONT_URL, ssl=self._ssl) as r:
            response = await r.text()
        bs = bs4.BeautifulSoup(response, "html.parser")
        token = bs.find("input", {"name":"__RequestVerificationToken"})["value"]
        assert isinstance(token, str)
        for script in bs.find_all("script"):
            if script.string is None:
                continue
            m = self.RETARD_PROTECTION_RE.search(script.string)
            if m is None:
                continue
            for op in RetardProtectionOp:
                if op.value == m[2]:
                    break
            else:
                continue
            rp = RetardProtection(int(m[1]), op)
            break
        else:
            raise RuntimeError("retard protection not found")
        return token, rp

    async def _api_request(self, method, **kwargs):
        async with self._rl:
            async with self._session.post("https://www.minsktrans.by/lookout_yard/Data/" + method,
                    ssl=self._ssl,
                    data=dict(**kwargs, __RequestVerificationToken=self._token),
                    headers={"Referer": self.FRONT_URL}) as r:
                if r.status != 200:
                    raise RuntimeError(method, kwargs, await r.text())
                return await r.json()

    async def route_list(self, transport_type=TransportType.Trolleybus, place=Place.Minsk):
        return await self._api_request("RouteList", p=place.value, tt=transport_type.value)

    async def track(self, route, transport_type=TransportType.Trolleybus, place=Place.Minsk):
        return await self._api_request("Track", r=route, p=place.value, tt=transport_type.value)

    async def route(self, route, transport_type=TransportType.Trolleybus, place=Place.Minsk):
        return await self._api_request("Route", r=route, p=place.value, tt=transport_type.value)

    async def vehicles(self, route, transport_type=TransportType.Trolleybus, place=Place.Minsk):
        return await self._api_request("Vehicles", r=route, p=place.value, tt=transport_type.value, v=self._rp(route))
