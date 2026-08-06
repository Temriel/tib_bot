import asyncio
from discord.ext import commands, tasks
from datetime import datetime, timedelta
from tib_utility.webhandler import WebHandler


TARGET_MINUTES = (1, 16, 31, 46) # pxls takes a hot sec to compile stats


class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._cached_stats = None
        self._cache_until = datetime.min

    def _next_cache_time(self, now: datetime) -> datetime:
        """Calculate the next cache time based on the current time."""
        for target in TARGET_MINUTES:
            if now.minute < target:
                return now.replace(minute=target, second=0, microsecond=0)
        return (now + timedelta(hours=1)).replace(minute=TARGET_MINUTES[0], second=0, microsecond=0)

    async def get_stats(self):
        now = datetime.now()
        if self._cached_stats is not None and now < self._cache_until:
            return self._cached_stats
        return await self.fetch_stats()
    
    async def fetch_stats(self):
        for attempt in range(4): # try once, if failed, try 3 more times
            try:
                handler = WebHandler()
                data = await asyncio.to_thread(handler.fetch_json)
                self._cached_stats = data
                self._cache_until = self._next_cache_time(datetime.now())
                return data
            except Exception as e:
                if attempt == 3:
                    print(f"Failed to fetch stats: {e}")
                    return None
                await asyncio.sleep(3)

    async def parse_stats(self, username, data=None):
        if data is None:
            data = await self.get_stats()
        if data is None:
            return None
        if isinstance(username, str):
            username = [username]
        elif isinstance(username, tuple):
            username = list(username)
        elif not isinstance(username, list):
            raise ValueError("username must be a string, list, or tuple")

        results = {}

        for userdata in data["toplist"]["canvas"]:
            current_username = userdata["username"]
            if current_username in username:
                results[current_username] = {"pixels": userdata["pixels"]}
                if len(results) == len(username):
                    break
        return results

#    @tasks.loop(seconds=60)
#    async def update_stats(self):
#        now = datetime.now()
#        minute = now.strftime("%M")
#        if int(minute) in TARGET_MINUTES:
#            try:
#                await self.fetch_stats()
#            except Exception as e:
#                print(f"Error fetching stats: {e}")
#
#    @update_stats.before_loop
#    async def before_update_stats(self):
#        await self.bot.wait_until_ready()