from redbot.core import commands, checks, data_manager, Config
import tempfile
import discord
import asyncio
import os
import random
import lavalink
import aiohttp
import easygTTS

class SFX(commands.Cog):
    """Plays uploaded sounds or text-to-speech."""

    def __init__(self):
        self.last_track_info = None
        self.current_sfx = None
        self.config = Config.get_conf(self, identifier=134621854878007296)
        self.sound_base = (data_manager.cog_data_path(self) / 'sounds').as_posix()
        self.session = aiohttp.ClientSession()
        self.gtts = easygTTS.gtts(session=self.session)
        guild_config = {
            'sounds': {}
        }
        global_config = {
            'sounds': {}
        }
        self.config.register_guild(**guild_config)
        self.config.register_global(**global_config)
        lavalink.register_event_listener(self.ll_check)
        if not os.path.exists(self.sound_base):
            os.makedirs(self.sound_base)

    def __unload(self):
        lavalink.unregister_event_listener(self.ll_check)

    @commands.command()
    @commands.cooldown(rate=1, per=1, type=discord.ext.commands.cooldowns.BucketType.guild)
    async def tts(self, ctx, *, text):
        """
        Plays the given text as TTS in your current voice channel.
        """

        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send('You are not connected to a voice channel.')
            return
        
        audio_file = os.path.join(tempfile.gettempdir(), ''.join(random.choice('0123456789ABCDEF') for i in range(12)) + '.mp3')
        gtts = easygTTS.gtts(session=self.session)
        tts = await gtts.get(text=text)
        with open(audio_file, "wb") as f:
            f.write(tts)
        await self._play_sfx(ctx.author.voice.channel, audio_file, True)

    @commands.command()
    @commands.cooldown(rate=1, per=1, type=discord.ext.commands.cooldowns.BucketType.guild)
    async def sfx(self, ctx, soundname: str):
        """
        Plays an existing sound in your current voice channel.
        """

        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send('You are not connected to a voice channel.')
            return

        if str(ctx.guild.id) not in os.listdir(self.sound_base):
            os.makedirs(os.path.join(self.sound_base, str(ctx.guild.id)))

        guild_sounds = await self.config.guild(ctx.guild).sounds()
        global_sounds = await self.config.sounds() # not used yet
        if soundname not in guild_sounds.keys():
            await ctx.send(f'Sound `{soundname}` does not exist. Try `{ctx.prefix}listsfx` for a list.')
            return

        filepath = os.path.join(self.sound_base, str(ctx.guild.id), guild_sounds[soundname])
        if not os.path.exists(filepath):
            del guild_sounds[soundname]
            await self.config.guild(ctx.guild).sounds.set(guild_sounds)
            await ctx.send('Looks like this sound\'s file has gone missing! I\'ve removed it from the list of sounds.')
            return

        await self._play_sfx(ctx.author.voice.channel, filepath)

    @commands.command()
    @checks.mod()
    async def addsfx(self, ctx, name: str, link: str=None):
        """Adds a new sound.

        Either upload the file as a Discord attachment and make your comment
        `[p]addsfx <name>`, or use `[p]addsfx <name> <direct-URL-to-file>`.
        """
        cfg_sounds = await self.config.guild(ctx.guild).sounds()

        if str(ctx.guild.id) not in os.listdir(self.sound_base):
            os.makedirs(os.path.join(self.sound_base, str(ctx.guild.id)))

        attach = ctx.message.attachments
        if len(attach) > 1 or (attach and link):
            await ctx.send('Please only add one sound at a time.')
            return

        url = ''
        filename = ''
        if attach:
            a = attach[0]
            url = a.url
            filename = a.filename
        elif link:
            url = ''.join(link)
            filename = os.path.basename(
                '_'.join(url.split()).replace('%20', '_'))
        else:
            await ctx.send('You must provide either a Discord attachment or a direct link to a sound.')
            return

        _, file_extension = os.path.splitext(filename)
        if file_extension != '.wav' and file_extension != '.mp3':
            await ctx.send('Only .wav and .mp3 sounds are currently supported.')
            return

        filepath = os.path.join(self.sound_base, str(ctx.guild.id), filename)

        if name in cfg_sounds.keys():
            await ctx.send('A sound with that name already exists. Please choose another name and try again.')
            return

        if os.path.exists(filepath):
            await ctx.send('A sound with that filename already exists. Please change the filename and try again.')
            return

        async with self.session.get(url) as new_sound:
            f = open(filepath, 'wb')
            f.write(await new_sound.read())
            f.close()

        cfg_sounds[name] = filename
        await self.config.guild(ctx.guild).sounds.set(cfg_sounds)

        await ctx.send(f'Sound {name} added.')

    @commands.command()
    @commands.is_owner()
    async def addglobalsfx(self, ctx, name: str, link: str=None):
        """Adds a new sound globally.

        Either upload the file as a Discord attachment and make your comment
        `[p]addglobalsfx <name>`, or use `[p]addglobalsfx <name> <direct-URL-to-file>`.
        """

        global_sounds = await self.config.sounds()

        attach = ctx.message.attachments
        if len(attach) > 1 or (attach and link):
            await ctx.send('Please only add one sound at a time.')
            return

        url = ''
        filename = ''
        if attach:
            a = attach[0]
            url = a.url
            filename = a.filename
        elif link:
            url = ''.join(link)
            filename = os.path.basename(
                '_'.join(url.split()).replace('%20', '_'))
        else:
            await ctx.send('You must provide either a Discord attachment or a direct link to a sound.')
            return

        _, file_extension = os.path.splitext(filename)
        if file_extension != '.wav' and file_extension != '.mp3':
            await ctx.send('Only .wav and .mp3 sounds are currently supported.')
            return

        filepath = os.path.join(self.sound_base, filename)

        if name in global_sounds.keys():
            await ctx.send('A sound with that name already exists. Please choose another name and try again.')
            return

        if os.path.exists(filepath):
            await ctx.send('A sound with that filename already exists. Please change the filename and try again.')
            return

        async with self.session.get(url) as new_sound:
            f = open(filepath, 'wb')
            f.write(await new_sound.read())
            f.close()

        global_sounds[name] = filename
        await self.config.sounds.set(global_sounds)

        await ctx.send(f'Sound {name} added.')

    @commands.command()
    @checks.mod()
    async def delsfx(self, ctx, soundname: str):
        """Deletes an existing sound."""

        if str(ctx.guild.id) not in os.listdir(self.sound_base):
            os.makedirs(os.path.join(self.sound_base, str(ctx.guild.id)))

        cfg_sounds = await self.config.guild(ctx.guild).sounds()

        if soundname not in cfg_sounds.keys():
            await ctx.send(f'Sound `{soundname}` does not exist. Try `{ctx.prefix}listsfx` for a list.')
            return

        filepath = os.path.join(self.sound_base, str(ctx.guild.id), cfg_sounds[soundname])

        if os.path.exists(filepath):
            os.remove(filepath)

        del cfg_sounds[soundname]
        await self.config.guild(ctx.guild).sounds.set(cfg_sounds)

        await ctx.send(f'Sound {soundname} deleted.')

    @commands.command()
    @checks.is_owner()
    async def delglobalsfx(self, ctx, soundname: str):
        """Deletes an existing global sound."""

        global_sounds = await self.config.sounds()

        if soundname not in global_sounds.keys():
            await ctx.send(f'Sound `{soundname}` does not exist. Try `{ctx.prefix}listsfx` for a list.')
            return

        filepath = os.path.join(self.sound_base, global_sounds[soundname])

        if os.path.exists(filepath):
            os.remove(filepath)

        del global_sounds[soundname]
        await self.config.sounds.set(global_sounds)

        await ctx.send(f'Sound {soundname} deleted.')

    @commands.command()
    @commands.cooldown(rate=1, per=3, type=discord.ext.commands.cooldowns.BucketType.guild)
    async def listsfx(self, ctx):
        """Prints all available sounds for this server."""

        if str(ctx.guild.id) not in os.listdir(self.sound_base):
            os.makedirs(os.path.join(self.sound_base, str(ctx.guild.id)))

        cfg_sounds = await self.config.guild(ctx.guild).sounds()

        if len(cfg_sounds.items()) == 0:
            await ctx.send(f'No sounds found. Use `{ctx.prefix}addsfx` to add one.')
            return

        paginator = discord.ext.commands.help.Paginator()
        for soundname, filepath in cfg_sounds.items():
            paginator.add_line(soundname)

        await ctx.send('Sounds for this server:')
        for page in paginator.pages:
            await ctx.send(page)



    async def _play_sfx(self, vc, filepath, is_tts=False):
        player = await lavalink.connect(vc)
        track = (await player.get_tracks(query=filepath))[0]

        if player.current is None:
            player.queue.append(track)
            self.current_sfx = (track, is_tts)
            await player.play()
            return

        if self.current_sfx is not None:
            player.queue.insert(0, track)
            await player.skip()
            if self.current_sfx[1]:
                os.remove(self.current_sfx[0].uri)
            self.current_sfx = (track, is_tts)
            return

        self.last_track_info = (player.current, player.position)
        self.current_sfx = (track, is_tts)
        player.queue.insert(0, track)
        player.queue.insert(1, player.current)
        await player.skip()

    async def ll_check(self, player, event, reason):
        if self.current_sfx is None and self.last_track_info is None:
            return

        if event == lavalink.LavalinkEvents.TRACK_EXCEPTION and self.current_sfx is not None:
            if self.current_sfx[1]:
                os.remove(self.current_sfx[0].uri)
            self.current_sfx = None
            return

        if event == lavalink.LavalinkEvents.TRACK_STUCK and self.current_sfx is not None:
            if self.current_sfx[1]:
                os.remove(self.current_sfx[0].uri)
            self.current_sfx = None
            await player.skip()
            return

        if event == lavalink.LavalinkEvents.TRACK_END and player.current is None and self.current_sfx is not None:
            if self.current_sfx[1]:
                os.remove(self.current_sfx[0].uri)
            self.current_sfx = None
            return

        if event == lavalink.LavalinkEvents.TRACK_END and self.last_track_info is not None and player.current.track_identifier == self.last_track_info[0].track_identifier:
            print(str(self.last_track_info[0].uri))
            if self.current_sfx[1]:
                os.remove(self.current_sfx[0].uri)
            self.current_sfx = None
            await player.pause()
            await player.seek(self.last_track_info[1])
            await player.pause(False)
            self.last_track_info = None
