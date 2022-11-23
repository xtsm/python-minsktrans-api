import asyncio
import json
import time

from minsktrans import MinsktransClient, TransportType, Place


async def fetch_numbers(c, tt, p, nums):
    while True:
        route_list = await c.route_list(tt, p)
        print(json.dumps({"method": "RouteList", "ts": time.time(), "tt": tt.value, "p": p.value, "response": route_list}))
        nums[(tt, p)] = [route["Number"] for route in route_list["Routes"]]
        await asyncio.sleep(43200)


async def fetch_routes(c, tt, p, nums):
    while True:
        if (tt, p) not in nums:
            await asyncio.sleep(5)
            continue

        for num in nums[(tt, p)]:
            track = await c.track(num, tt, p)
            print(json.dumps({"method": "Track", "ts": time.time(), "tt": tt.value, "p": p.value, "r": num, "response": track}))
            route = await c.route(num, tt, p)
            print(json.dumps({"method": "Route", "ts": time.time(), "tt": tt.value, "p": p.value, "r": num, "response": route}))

        await asyncio.sleep(3600)


async def fetch_vehicles(c, tt, p, nums):
    while True:
        if (tt, p) not in nums or len(nums[(tt, p)]) == 0:
            await asyncio.sleep(5)
            continue

        for num in nums[(tt, p)]:
            vehicles = await c.vehicles(num, tt, p)
            print(json.dumps({"method": "Vehicles", "ts": time.time(), "tt": tt.value, "p": p.value, "r": num, "response": vehicles}))


async def main():
    async with MinsktransClient() as c:
        tasks = []
        nums = {}
        for p in Place:
            for tt in TransportType:
                tasks.append(fetch_numbers(c, tt, p, nums))
                tasks.append(fetch_routes(c, tt, p, nums))
                tasks.append(fetch_vehicles(c, tt, p, nums))
        await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
