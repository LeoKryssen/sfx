import asyncio
import os
import unicodedata

import aiofiles
import aiohttp
import discord
import lavalink
import pydub
import unidecode
from redbot.core import Config, checks, commands, data_manager
from redbot.core.utils.chat_formatting import pagify
from redbot.core.utils.predicates import MessagePredicate

from .api import generate_urls

try:
    from redbot.core.utils._dpy_menus_utils import dpymenu

    DPY_MENUS = True
except ImportError:
    from redbot.core.utils.menus import DEFAULT_CONTROLS, menu

from .voices import voices


class SFX(commands.Cog):
    """Plays uploaded sounds or text-to-speech."""

    __version__ = "2.0.0.dev1"

    def __init__(self, bot):
        self.bot = bot
        self.last_track_info = None
        self.current_sfx = None
        self.config = Config.get_conf(self, identifier=134621854878007296)
        self.sound_base = (data_manager.cog_data_path(self) / "sounds").as_posix()
        self.session = aiohttp.ClientSession()
        user_config = {"voice": "clara", "speed": 5}
        guild_config = {"sounds": {}, "channels": []}
        global_config = {"sounds": {}, "schema_version": 0}
        self.config.register_user(**user_config)
        self.config.register_guild(**guild_config)
        self.config.register_global(**global_config)
        lavalink.register_event_listener(self.ll_check)
        if not os.path.exists(self.sound_base):
            os.makedirs(self.sound_base)
        self.bot.loop.create_task(self.check_config_version())
        self.check_audio_loaded()
        self.queue = asyncio.Queue()

    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())
        lavalink.unregister_event_listener(self.ll_check)

    def format_help_for_context(self, ctx):
        """Thanks Sinbad"""
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\nCog Version: {self.__version__}"

    async def check_config_version(self):
        schema_version = await self.config.schema_version()
        if schema_version == 0:
            all_users = await self.config.all_users()
            for user in all_users:
                await self.config.user_from_id(user).speed.set(5)
            await self.config.schema_version.set(1)

    def check_audio_loaded(self):
        audio = self.bot.get_cog("Audio")
        if not audio:
            raise RuntimeError(
                "The audio cog needs to be loaded for this cog to function."
            )

    def pad_sfx(filepath):
        audio_data = pydub.AudioSegment.from_file(filepath)
        silence = pydub.AudioSegment.silent(duration=750)
        padded_audio = silence + audio_data
        padded_audio.export(filepath)

    # full credits to kable
    # https://github.com/kablekompany/Kable-Kogs/blob/master/decancer/decancer.py#L67
    @staticmethod
    def decancer_text(text):
        text = unicodedata.normalize("NFKC", text)
        text = unicodedata.normalize("NFD", text)
        text = unidecode.unidecode(text)
        text = text.encode("ascii", "ignore")
        text = text.decode("utf-8")
        if text == "":
            return
        return text

    @commands.command()
    @commands.cooldown(
        rate=1, per=1, type=discord.ext.commands.cooldowns.BucketType.guild
    )
    @commands.guild_only()
    async def tts(self, ctx, *, text):
        """
        Plays the given text as TTS in your current voice channel.
        """

        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send("You are not connected to a voice channel.")
            return

        author_data = await self.config.user(ctx.author).all()
        author_voice = author_data["voice"]
        author_speed = author_data["speed"]

        text = self.decancer_text(text)

        if text is None:
            await ctx.send("That's not a valid message, sorry.")
            return

        char_number = len(text)

        if char_number > 1000:
            await ctx.send(
                f"Sorry, I limit TTS to 1000 characters to avoid abuse. ({char_number}/1000)"
            )
            return

        urls = generate_urls(author_voice, text, author_speed)

        try:
            await self._play_sfx(ctx.author.voice.channel, urls, True)
        except Exception:
            await ctx.send(
                "Oops, an error occured. If this continues please use the contact command to inform the bot owner."
            )

    @commands.command()
    @commands.cooldown(
        rate=1, per=1, type=discord.ext.commands.cooldowns.BucketType.guild
    )
    @commands.guild_only()
    async def sfx(self, ctx, sound: str):
        """
        Plays an existing sound in your current voice channel.
        If a guild SFX exists with the same name as a global one, the guild SFX will be played.
        """

        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send("You are not connected to a voice channel.")
            return

        if str(ctx.guild.id) not in os.listdir(self.sound_base):
            os.makedirs(os.path.join(self.sound_base, str(ctx.guild.id)))

        guild_sounds = await self.config.guild(ctx.guild).sounds()
        global_sounds = await self.config.sounds()

        if sound not in guild_sounds.keys():
            if sound not in global_sounds.keys():
                await ctx.send(
                    f"Sound **{sound}** does not exist. Try `{ctx.clean_prefix}listsfx` for a list."
                )
                return

        if sound in guild_sounds.keys():
            filepath = os.path.join(
                self.sound_base, str(ctx.guild.id), guild_sounds[sound]
            )
        else:
            filepath = os.path.join(self.sound_base, global_sounds[sound])

        if not os.path.exists(filepath):
            if sound in guild_sounds.keys():
                del guild_sounds[sound]
                await self.config.guild(ctx.guild).sounds.set(guild_sounds)
                await ctx.send(
                    "Uh oh, it looks like the file was manually deleted. I've removed it from my list this won't happen again."
                )
                if sound in global_sounds.keys():
                    del global_sounds[sound]
                    await self.config.sounds.set(global_sounds)
                    await ctx.send(
                        "Uh oh, it looks like the file was manually deleted. I've removed it from my list this won't happen again."
                    )
                    return
                else:
                    return
            elif sound in global_sounds.keys():
                del global_sounds[sound]
                await self.config.sounds.set(global_sounds)
                await ctx.send(
                    "Uh oh, it looks like the file was manually deleted. I've removed it from my list this won't happen again."
                )
                if sound in global_sounds.keys():
                    del global_sounds[sound]
                    await self.config.sounds.set(global_sounds)
                    await ctx.send(
                        "Uh oh, it looks like the file was manually deleted. I've removed it from my list this won't happen again."
                    )
                return

        try:
            await self._play_sfx(ctx.author.voice.channel, filepath)
        except Exception:
            await ctx.send(
                "Oops, an error occured. If this continues please use the contact command to inform the bot owner."
            )

    @commands.command()
    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    async def addsfx(self, ctx, name: str, link: str = None):
        """
        Adds a new SFX to this guild.
        Either upload the file as a Discord attachment or use a link.

        Syntax:`[p]addsfx <name>` or `[p]addsfx <name> <link>`.
        """
        guild_sounds = await self.config.guild(ctx.guild).sounds()

        if str(ctx.guild.id) not in os.listdir(self.sound_base):
            os.makedirs(os.path.join(self.sound_base, str(ctx.guild.id)))

        attachments = ctx.message.attachments
        if len(attachments) > 1 or (attachments and link):
            await ctx.send("Please only try to add one SFX at a time.")
            return

        url = ""
        filename = ""
        if attachments:
            attachment = attachments[0]
            url = attachment.url
            filename = attachment.filename
        elif link:
            url = "".join(link)
            filename = "".join(url.split("/")[-1:]).replace("%20", "_")
        else:
            await ctx.send(
                "You must provide either a Discord attachment or a direct link to a sound."
            )
            return

        file_name, file_extension = os.path.splitext(filename)
        if file_extension != ".wav" and file_extension != ".mp3":
            await ctx.send(
                "Sorry, only SFX in .mp3 and .wav format are supported at this time."
            )
            return

        filepath = os.path.join(self.sound_base, str(ctx.guild.id), filename)

        if name in guild_sounds.keys():
            await ctx.send(
                f"A sound with that filename already exists. Either choose a new name or use {ctx.clean_prefix}delsfx to remove it."
            )
            return

        if os.path.exists(filepath):
            await ctx.send(
                "A sound with that filename already exists. Please change the filename and try again."
            )
            return

        async with self.session.get(url) as new_sound:
            f = await aiofiles.open(filepath, mode="wb")
            await f.write(await new_sound.read())
            await f.close()

        await self.bot.loop.run_in_executor(None, self.pad_sfx, filepath)

        guild_sounds[name] = filename
        await self.config.guild(ctx.guild).sounds.set(guild_sounds)

        await ctx.send(f"Sound **{name}** has been added.")

    @commands.command()
    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    async def delsfx(self, ctx, soundname: str):
        """
        Deletes an existing sound.
        """

        if str(ctx.guild.id) not in os.listdir(self.sound_base):
            os.makedirs(os.path.join(self.sound_base, str(ctx.guild.id)))

        cfg_sounds = await self.config.guild(ctx.guild).sounds()

        if soundname not in cfg_sounds.keys():
            await ctx.send(
                f"Sound **{soundname}** does not exist. Try `{ctx.prefix}listsfx` for a list."
            )
            return

        filepath = os.path.join(
            self.sound_base, str(ctx.guild.id), cfg_sounds[soundname]
        )

        if os.path.exists(filepath):
            await self.bot.loop.run_in_executor(None, os.remove, filepath)

        del cfg_sounds[soundname]
        await self.config.guild(ctx.guild).sounds.set(cfg_sounds)

        await ctx.send(f"Sound **{soundname}** deleted.")

    @commands.command()
    @commands.is_owner()
    @commands.guild_only()
    async def addglobalsfx(self, ctx, name: str, link: str = None):
        """
        Adds a new SFX to this the bot globally.
        Either upload the file as a Discord attachment or use a link.

        Syntax:`[p]addsfx <name>` or `[p]addsfx <name> <link>`.
        """
        global_sounds = await self.config.sounds()

        if str(ctx.guild.id) not in os.listdir(self.sound_base):
            os.makedirs(os.path.join(self.sound_base, str(ctx.guild.id)))

        attachments = ctx.message.attachments
        if len(attachments) > 1 or (attachments and link):
            await ctx.send("Please only try to add one SFX at a time.")
            return

        url = ""
        filename = ""
        if attachments:
            attachment = attachments[0]
            url = attachment.url
            filename = attachment.filename
        elif link:
            url = "".join(link)
            filename = "".join(url.split("/")[-1:]).replace("%20", "_")
        else:
            await ctx.send(
                "You must provide either a Discord attachment or a direct link to a sound."
            )
            return

        file_name, file_extension = os.path.splitext(filename)
        if file_extension != ".wav" and file_extension != ".mp3":
            await ctx.send(
                "Sorry, only SFX in .mp3 and .wav format are supported at this time."
            )
            return

        filepath = os.path.join(self.sound_base, filename)

        if name in global_sounds.keys():
            await ctx.send(
                f"A sound with that filename already exists. Either choose a new name or use {ctx.clean_prefix}delglobalsfx to remove it."
            )
            return

        if os.path.exists(filepath):
            await ctx.send(
                "A sound with that filename already exists. Please change the filename and try again."
            )
            return

        async with self.session.get(url) as new_sound:
            f = await aiofiles.open(filepath, mode="wb")
            await f.write(await new_sound.read())
            await f.close()

        await self.bot.loop.run_in_executor(None, self.pad_sfx, filepath)

        global_sounds[name] = filename
        await self.config.sounds.set(global_sounds)

        await ctx.send(f"Sound **{name}** has been added.")

    @commands.command()
    @checks.is_owner()
    async def delglobalsfx(self, ctx, soundname: str):
        """
        Deletes an existing global sound.
        """

        global_sounds = await self.config.sounds()

        if soundname not in global_sounds.keys():
            await ctx.send(
                f"Sound **{soundname}** does not exist. Try `{ctx.prefix}listsfx` for a list."
            )
            return

        filepath = os.path.join(self.sound_base, global_sounds[soundname])

        if os.path.exists(filepath):
            await self.bot.loop.run_in_executor(None, os.remove, filepath)

        del global_sounds[soundname]
        await self.config.sounds.set(global_sounds)

        await ctx.send(f"Sound **{soundname}** deleted.")

    @commands.command()
    @commands.guild_only()
    async def listsfx(self, ctx):
        """
        Lists all available sounds for this server.
        """

        if str(ctx.guild.id) not in os.listdir(self.sound_base):
            await self.bot.loop.run_in_executor(
                None, os.makedirs, os.path.join(self.sound_base, str(ctx.guild.id))
            )

        guild_sounds = await self.config.guild(ctx.guild).sounds()
        global_sounds = await self.config.sounds()

        if (len(guild_sounds.items()) + len(global_sounds.items())) == 0:
            await ctx.send(f"No sounds found. Use `{ctx.prefix}addsfx` to add one.")
            return

        txt = ""

        if guild_sounds:
            txt += "**Guild Sounds**:\n"
            for sound in guild_sounds:
                txt += sound + "\n"

        if global_sounds:
            txt += "\n**Global Sounds**:\n"
            for sound in global_sounds:
                if guild_sounds:
                    if sound in guild_sounds:
                        txt += sound + " (disabled)\n"
                txt += sound + "\n"

        pages = [p for p in pagify(text=txt, delims="\n")]

        for page in pages:
            await ctx.send(page)

    @commands.command(aliases=["setvoice"])
    async def myvoice(self, ctx, voice: str = None):
        """
        Changes your TTS voice.
        Type `[p]listvoices` to view all possible voices.
        If no voice is provided, it will show your current voice.
        """

        current_voice = await self.config.user(ctx.author).voice()

        if voice is None:
            await ctx.send(f"Your current voice is **{current_voice}**")
            return
        voice = voice.title()
        if voice in voices.keys():
            await self.config.user(ctx.author).voice.set(voice)
            await ctx.send(f"Your new TTS voice is: **{voice}**")
        else:
            await ctx.send(
                f"Sorry, that's not a valid voice. You can view voices with the `{ctx.clean_prefix}listvoices` command."
            )

    @commands.command(aliases=["setspeed"])
    async def myspeed(self, ctx, speed: int = None):
        """
        Changes your TTS speed.
        If no speed is provided, it will show your current speed.
        The speed range is 0-10 (higher is faster, 5 is normal.)
        """
        author_data = await self.config.user(ctx.author).all()
        current_speed = author_data["speed"]
        current_voice = author_data["voice"]
        support_speed = voices[current_voice]["speed"]

        if speed is None:
            await ctx.send(f"Your current speed is **{current_speed}**")
            return
        if speed < 0:
            await ctx.send("Your speed must be greater than or equal to 0.")
            return
        if speed > 10:
            await ctx.send("Your speed must be less than or equal to 10.")
            return

        await self.config.user(ctx.author).speed.set(speed)
        if support_speed:
            await ctx.send(f"Your new speed is **{speed}**.")
        else:
            await ctx.send(
                f"Your new speed is **{speed}**.\n"
                "Keep in mind your current voice doesn't support speed changes, "
                "so you won't see a difference until you change your voice to one that supports speed."
            )

    @commands.command()
    async def listlangs(self, ctx):
        """
        List all the valid language codes for TTS voices.
        """
        langs = sorted(
            set([voices[voice]["languageCode"] for voice in voices.keys()] + ["all"])
        )
        embed = discord.Embed(
            title="Valid Language Codes",
            color=await ctx.embed_color(),
            description=", ".join(langs),
        )
        await ctx.send(embed=embed)

    @commands.command()
    async def listvoices(self, ctx, lang="en"):
        """
        Lists all the TTS voices in the selected language.

        If no language is provided, it will list sthe voices in English.
        Use 'all' as the language code to view all voices.
        """
        langs = set([voices[voice]["languageCode"] for voice in voices.keys()])
        ALL_VOICES = False
        if lang not in langs:
            if lang == "all":
                ALL_VOICES = True
            else:
                await ctx.send(
                    f"Sorry, that's not a valid language code. You can view all valid language codes with the `{ctx.clean_prefix}listlangs` command."
                )
        if ALL_VOICES:
            voice_data = voices
        else:
            voice_data = {
                voice: voices[voice]
                for voice in voices.keys()
                if voices[voice]["languageCode"] == lang
            }
        low = []
        medium = []
        high = []
        for voice in voice_data:
            embed = discord.Embed(color=await ctx.embed_color(), title=voice)
            embed.description = (
                "```yaml\n"
                f"Gender: {voice_data[voice]['gender']}\n"
                f"Language: {voice_data[voice]['languageName']}\n"
                f"Quality: {voice_data[voice]['quality']}\n"
                f"Provider: {voice_data[voice]['provider']}"
                "```"
            )
            if voice_data[voice]["quality"] == "Low":
                low.append(embed)
            elif voice_data[voice]["quality"] == "Medium":
                medium.append(embed)
            elif voice_data[voice]["quality"] == "High":
                high.append(embed)
        pages = high + medium + low

        for index, embed in enumerate(pages):
            if len(pages) > 1:
                embed.set_footer(text=f"Voice {index + 1}/{len(pages)} | {lang} voices")

        if DPY_MENUS:
            await dpymenu(ctx, pages, timeout=60)
        else:
            if len(pages) == 1:
                await ctx.send(embed=pages[0])
            else:
                await menu(ctx, pages, DEFAULT_CONTROLS, timeout=60)

    @commands.group()
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def ttschannel(self, ctx):
        """
        Configures automatic TTS channels.
        """
        pass

    @ttschannel.command()
    async def add(self, ctx, channel: discord.TextChannel):
        """
        Adds a channel for automatic TTS.
        """
        channel_list = await self.config.guild(ctx.guild).channels()
        if channel.id not in channel_list:
            channel_list.append(channel.id)
            await self.config.guild(ctx.guild).channels.set(channel_list)
            await ctx.send(
                f"Okay, {channel.mention} will now be used as a TTS channel."
            )
        else:
            await ctx.send(
                f"{channel.mention} is already a TTS channel, did you mean use the `{ctx.clean_prefix}ttschannel remove` command?"
            )

    @ttschannel.command(aliases=["delete", "del"])
    async def remove(self, ctx, channel: discord.TextChannel):
        """
        Removes a channel for automatic TTS.
        """
        channel_list = await self.config.guild(ctx.guild).channels()
        if channel.id in channel_list:
            channel_list.remove(channel.id)
            await self.config.guild(ctx.guild).channels.set(channel_list)
            await ctx.send(f"Okay, {channel.mention} is no longer a TTS channel.")
        else:
            await ctx.send(
                f"{channel.mention} isn't a TTS channel, did you mean use the `{ctx.clean_prefix}ttschannel add` command?"
            )

    @ttschannel.command()
    async def clear(self, ctx):
        """
        Removes all the channels for automatic TTS.
        """
        channel_list = await self.config.guild(ctx.guild).channels()
        if not channel_list:
            await ctx.send("There's no channels in the config.")
        else:
            try:
                await ctx.send(
                    "Are you sure you want to clear all this server's TTS channels? Respond with yes or no."
                )
                predictate = MessagePredicate.yes_or_no(ctx, user=ctx.author)
                await ctx.bot.wait_for("message", check=predictate, timeout=30)
            except asyncio.TimeoutError:
                await ctx.send(
                    "You never responded, please use the command again to clear all of this server's TTS channels."
                )
                return
            if predictate.result:
                await self.config.guild(ctx.guild).channels.set([])
                await ctx.send("Okay, I've cleared all TTS channels for this server.")
            else:
                await ctx.send("Okay, I won't clear any TTS channels.")

    @ttschannel.command()
    async def list(self, ctx):
        """
        Shows all the channels for automatic TTS.
        """
        channel_list = await self.config.guild(ctx.guild).channels()
        if not channel_list:
            await ctx.send("This server doesn't have any TTS channels set up.")
        else:
            text = ""
            for channel in channel_list:
                text += "<#" + str(channel) + "> - " + str(channel) + "\n"
            pages = [p for p in pagify(text=text, delims="\n")]
            embeds = []
            for index, page in enumerate(pages):
                embed = discord.Embed(
                    title="Automatic TTS Channels",
                    color=await ctx.embed_colour(),
                    description=page,
                )
                if len(embeds) > 1:
                    embed.set_footer(text=f"Page {index+1}/{len(pages)}")
                embeds.append(embed)

            if DPY_MENUS:
                await dpymenu(ctx, embeds, timeout=60)
            else:
                if len(pages) == 1:
                    await ctx.send(embed=embeds[0])
                else:
                    await menu(ctx, embeds, DEFAULT_CONTROLS, timeout=60)

    @commands.Cog.listener()
    async def on_message_without_command(self, message: discord.Message):
        if not message.guild:
            return
        if message.author.bot:
            return
        if not message.channel.permissions_for(message.guild.me).send_messages:
            return
        if await self.bot.allowed_by_whitelist_blacklist(who=message.author) is False:
            return
        if await self.bot.cog_disabled_in_guild(self, message.guild):
            return

        channel_list = await self.config.guild(message.guild).channels()

        if not channel_list:
            return
        if message.channel.id not in channel_list:
            return

        if not message.author.voice or not message.author.voice.channel:
            await message.channel.send("You are not connected to a voice channel.")
            return

        author_data = await self.config.user(message.author).all()
        author_voice = author_data["voice"]
        author_speed = author_data["speed"]

        text = self.decancer_text(message.clean_content)

        if text is None:
            await message.channel.send("That's not a valid message, sorry.")
            return

        char_number = len(text)

        if char_number > 1000:
            await message.channel.send(
                f"Sorry, I limit TTS to 1000 characters to avoid abuse. ({char_number}/1000)"
            )
            return

        urls = generate_urls(author_voice, text, author_speed)

        try:
            await self._play_sfx(message.author.voice.channel, urls, True)
        except Exception:
            await message.channel.send(
                "Oops, an error occured. If this continues please use the contact command to inform the bot owner."
            )

    async def _play_sfx(self, vc, filepath, is_tts=False):
        player = await lavalink.connect(vc)

    async def ll_check(self, player, event, reason):
        pass
