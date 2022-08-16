import discord
from discord.ext import commands, tasks
from newspaper import Article, Config
from gtts import gTTS
from slugify import slugify
from itertools import cycle
from urllib.parse import urlparse
from urlextract import URLExtract
from sqlitedict import SqliteDict
from asyncio import TimeoutError
from moviepy.editor import ColorClip, AudioFileClip, ImageClip
from textwrap import TextWrapper
from datetime import datetime
import os
from pydantic import BaseSettings
from typing import List

class Settings(BaseSettings):
    token = ""
    guild = int
    channels = [int]

    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'

settings = Settings()

wrapper = TextWrapper()
wrapper.width = 120
wrapper.fix_sentence_endings = True
wrapper.break_long_words = False
wrapper.break_on_hyphens = False

db = SqliteDict("db.sqlite", autocommit=True)

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="$", description="Reads news articles.", intents=intents)

status = cycle(["run $help for more"])

USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:78.0) Gecko/20100101 Firefox/78.0'

config = Config()
config.browser_user_agent = USER_AGENT


@tasks.loop(seconds=10)
async def changeStatus():
    await bot.change_presence(
        status=discord.Status.do_not_disturb,
        activity=discord.Activity(
            type=discord.ActivityType.watching, name=next(status)
        ),
    )


@bot.group(name="list", invoke_without_command=True)
async def _list(ctx):
    """Show or edit accepted domains for articles"""
    pass


@_list.command(name="all")
async def all(ctx):
    """List all domains in the database"""
    msg = "**Paperboy database**:\n"
    for netloc, value in db.items():
        msg = msg + f"**{netloc}**: {value}\n"
    await ctx.send(msg)


@_list.command(name="add")
async def add(ctx, url):
    """Add a domain to the whitelist"""
    url_parsed = urlparse(url)
    if str(url_parsed.netloc) not in db:
        db[url_parsed.netloc] = {"whitelist": True}
    else:
        url_profile = db[url_parsed.netloc]
        url_profile["whitelist"] = True
        db[url_parsed.netloc] = url_profile
    await ctx.send(f"**{url_parsed.netloc}**: {db[url_parsed.netloc]}")


@_list.command(name="rm")
async def rm(ctx, url):
    """Remove a domain from the whitelist"""
    url_parsed = urlparse(url)
    if str(url_parsed.netloc) not in db:
        await ctx.send(f"**{url_parsed.netloc}** not found in database.")
        return
    del db[url_parsed.netloc]
    await ctx.send(f"**{url_parsed.netloc}** removed from database.")


@bot.command(name="ping", description="Check response.")
async def ping(ctx):
    """Measure the ping between discord and the bot"""
    print("ping pong")
    channel = ctx.message.channel
    t1 = time.perf_counter()
    async with ctx.typing():
        t2 = time.perf_counter()
    await ctx.send("Ping: {}ms".format(round((t2 - t1) * 1000)))


@bot.event
async def on_ready():
    for guild in bot.guilds:
        if guild.id == settings.guild:
            break
    changeStatus.start()
    # guild = discord.utils.find(lambda g: g.id == GUILD, client.guilds)
    # guild = discord.utils.get(client.guilds, id=GUILD)
    print(
        f"{bot.user} is connected to the following guild:\n"
        f"{guild.name}(id: {guild.id})"
    )

def color_clip(audio, fps=14, color=(0,0,0)):
    output = f"{audio.replace('.mp3', '.webm')}"
    size = (200, 100)
    audioclip = AudioFileClip(audio)
    clip = ImageClip("cat_paper.jpg", duration=audioclip.duration)
    #clip = ColorClip(size, color, duration=audioclip.duration)
    videoclip = clip.set_audio(audioclip)
    videoclip.write_videofile(output, fps=fps)
    return output

async def process_article(url, message):
    await message.add_reaction("📰")
    await bot.change_presence(
        status=discord.Status.do_not_disturb,
        activity=discord.Activity(
            type=discord.ActivityType.playing, name="busy doing shit"
        ),
    )
    async with message.channel.typing():
        article = Article(url, config=config)
        print("downlowding article")
        article.download()
        print("parsing article")
        article.parse()
        print("running nlp on article")
        article.nlp()
        print("running text to speech")
        text = "\n".join(wrapper.wrap(article.text))
        tts = gTTS(text=text, lang="en", slow=False)
        audio_file_name = f"{slugify(article.title)}.mp3"
        text_file_name = f"{slugify(article.title)}.txt"
        tts.save(f"./articles/{audio_file_name}")
        print("running video conversion")
        video_file_name = color_clip(f"./articles/{audio_file_name}")
        with open(f"./articles/{text_file_name}", 'w') as txt:
            txt.write(text)
        meta = f"By: __{','.join(article.authors or [])}__ {article.publish_date or datetime.min:%Y-%m-%d}\n"
        print("uploading article to discord")
        await message.channel.send(
            f"**SUMMARY: {article.title}**\n{meta}{article.summary[:2000]}",
            file=discord.File(video_file_name),
            reference=message,
        )
        print("finished")


@bot.event
async def on_message(message):
    username = str(message.author).split("#")[0]
    channel = message.channel.name
    user_message = str(message.content)

    if message.channel.id not in settings.channels:
        return
    if message.author == bot.user:
        return
    if user_message and user_message[0] == "$":
        await bot.process_commands(message)
        return
    print(f"Message {user_message} by {username} on {channel}")

    extractor = URLExtract()
    urls = extractor.find_urls(user_message)
    for url in urls:
        url_parsed = urlparse(url)
        if url_parsed.netloc not in db:

            def check(reaction, user):
                return (
                    reply.id == reaction.message.id
                    and user == message.author
                    and str(reaction.emoji) == "✅"
                )

            reply = await message.channel.send(
                f"**{url_parsed.netloc}** not known, react with ✅ to add to whitelist and parse.",
                reference=message,
            )
            await reply.add_reaction("✅")
            try:
                reaction, user = await bot.wait_for(
                    "reaction_add", timeout=60.0, check=check
                )
            except TimeoutError:
                await reply.delete()
            else:
                await reply.delete()
                await process_article(url, message)

            db[url_parsed.netloc] = {"whitelist": False}

        url_profile = db[url_parsed.netloc]
        if url_profile["whitelist"]:
            await process_article(url, message)


bot.run(settings.token)  # , log_handler=handler)
