from aiohttp.multipart import BadContentDispositionHeader
from redbot.core.bot import Red
from .sfx import SFX

async def setup(bot: Red) -> None:
    cog = SFX(bot)
    bot.add_cog(cog)

__red_end_user_data_statement__ = (
    "This cog does not store any end user data."
)