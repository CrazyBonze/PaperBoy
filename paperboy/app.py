import discord
from discord.ext import commands, tasks
from gtts import gTTS
from slugify import slugify
from itertools import cycle
from urllib.parse import urlparse
from urlextract import URLExtract
from sqlitedict import SqliteDict
from asyncio import TimeoutError
import asyncio
from aiohttp.client_exceptions import ClientOSError
from moviepy.editor import ColorClip, AudioFileClip, ImageClip, concatenate_audioclips
from datetime import datetime
import os
from pydantic import BaseSettings
from selenium import webdriver
#import chromedriver_autoinstaller
from selenium.webdriver.chrome.options import Options
import google.cloud.texttospeech as tts
from datetime import timedelta
from summerizer import summarize
from text_processing import process_text
import trafilatura
import tempfile
from courlan import check_url
import validators
import backoff
import nltk

nltk.download('punkt')

#os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/home/michael/PaperBoy/key.json"
SELENIUM_URL = "http://selenium:4444/wd/hub"


async def text_to_speech(filename: str, chunked_text: [str]):
    voice_params = tts.VoiceSelectionParams(
        language_code="en-US", name="en-US-Wavenet-I"
    )
    audio_config = tts.AudioConfig(audio_encoding=tts.AudioEncoding.LINEAR16)
    client = tts.TextToSpeechAsyncClient()
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_audio = []
        for i, text in enumerate(chunked_text):
            text_input = tts.SynthesisInput(text=text)
            response = await client.synthesize_speech(
                input=text_input, voice=voice_params, audio_config=audio_config
            )
            with open(f"{tmp_dir}/{i}.mp3", "wb") as out:
                out.write(response.audio_content)
                tmp_audio.append(AudioFileClip(out.name))
        concat_clip = concatenate_audioclips(tmp_audio)
        concat_clip.write_audiofile(filename)


#chromedriver_autoinstaller.install()
chrome_options = Options()
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-gpu')
chrome_options.add_argument("--headless")
chrome_options.add_argument("--window-size=1920x1080")


class Settings(BaseSettings):
    token = ""
    guild = int
    channels = [int]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

db = SqliteDict("db.sqlite", autocommit=True)

intents = discord.Intents.all()
bot = commands.Bot(
    command_prefix="$", description="Reads news articles.", intents=intents
)

status = cycle(["run $help for more"])

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:78.0) Gecko/20100101 Firefox/78.0"
)


@tasks.loop(seconds=15)
async def changeStatus():
    await bot.change_presence(
        status=discord.Status.idle,
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
    domain = ".".join([d for d in list(tldextract.extract(url)) if d])
    if validators.domain(domain) is not True:
        await ctx.send(f"No valid domain found in {url}.")
        return
    if domain not in db:
        db[domain] = {"whitelist": True, "paywall": False}
        await ctx.send(f"**{domain}**: {db[domain]}")
        return
    await ctx.send(f"**{domain}** already in database.")


@_list.command(name="rm")
async def rm(ctx, url):
    """Remove a domain from the whitelist"""
    url_parsed = urlparse(url)
    domain = str(url_parsed.netloc) or url
    if domain not in db:
        await ctx.send(f"**{url}** not found in database.")
        return
    del db[domain]
    await ctx.send(f"**{domain}** removed from database.")


@bot.command(name="paywall", description="Add or remove paywall.")
async def paywall(ctx, url):
    """Turn on and off paywall diversion."""
    url_parsed = urlparse(url)
    domain = str(url_parsed.netloc) or url
    if domain not in db:
        await ctx.send(f"**{url}** not found in database.")
        return
    url_profile = db[domain]
    url_profile["paywall"] = not url_profile["paywall"]
    db[domain] = url_profile
    await ctx.send(f"**{domain}**: {db[domain]}")


@bot.command(name="whitelist", description="Add or remove whitelist.")
async def whitelist(ctx, url):
    """Add or remove a domain from the whitelist."""
    url_parsed = urlparse(url)
    domain = str(url_parsed.netloc) or url
    if domain not in db:
        await ctx.send(f"**{url}** not found in database.")
        return
    url_profile = db[domain]
    url_profile["whitelist"] = not url_profile["whitelist"]
    db[domain] = url_profile
    await ctx.send(f"**{domain}**: {db[domain]}")


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

async def color_clip(audio):
    def make_video(audio):
        filename = f"{audio.replace('.mp3', '.webm')}"
        size = (200, 100)
        audioclip = AudioFileClip(audio)
        clip = ImageClip("cat_paper.jpg", duration=audioclip.duration + 0.1)
        # clip = ColorClip(size, color=(0, 0, 0), duration=audioclip.duration + 0.1)
        videoclip = clip.set_audio(audioclip)
        videoclip.write_videofile(filename, fps=1, audio_bitrate="84k", threads=4)
        return filename, timedelta(seconds=videoclip.duration)

    loop = asyncio.get_running_loop()
    done = loop.run_in_executor(None, make_video, audio)
    return await done


async def get_source(url):
    def divert_paywall(url):
        url_parsed = urlparse(url)
        url_profile = db[url_parsed.netloc]
        return url_profile["paywall"]

    def scrape(url):
        source = None
        if divert_paywall(url):
            driver = webdriver.Remote(SELENIUM_URL, options=chrome_options)
            driver.implicitly_wait(10)
            driver.get(f"https://12ft.io/{url}")
            driver.switch_to.frame(driver.find_element("xpath", "//iframe[1]"))
            source = driver.page_source
            driver.quit()
        else:
            driver = webdriver.Remote(SELENIUM_URL, options=chrome_options)
            driver.implicitly_wait(10)
            driver.get(url)
            source = driver.page_source
            driver.quit()
        return source

    loop = asyncio.get_running_loop()
    done = loop.run_in_executor(None, scrape, url)
    return await done


async def get_article(source, url):
    return trafilatura.bare_extraction(
        source,
        url=url,
        include_comments=False,
        include_tables=False,
        favor_precision=True,
    )

async def backoff_hdlr(details):
    print ("Backing off {wait:0.1f} seconds after {tries} tries "
           "calling function {target} with args {args} and kwargs "
           "{kwargs}".format(**details))

@backoff.on_exception(backoff.constant, ClientOSError, max_tries=3, interval=1, on_backoff=backoff_hdlr)
async def upload_message(text, video_file_name, reference):
    await reference.channel.send(
        text,
        files=[discord.File(video_file_name)], #, discord.File(f"./articles/{text_file_name}")],
        reference=reference,
    )


async def process_article(url, message):
    await message.add_reaction("📰")
    async with message.channel.typing():
        print("downlowding article")
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.playing, name="Reading article 📖"
            ),
        )
        # Divert paywall
        source = await get_source(url)

        print("parsing article")
        article = await get_article(source, url)
        audio_file_name = f"{slugify(article['title'])}.mp3"
        text_file_name = f"{slugify(article['title'])}.txt"

        print("running nlp on article")
        summary = await summarize(article["text"])
        # tts = gTTS(text=text, lang="en", slow=False)
        # tts.save(f"./articles/{audio_file_name}")

        print("running text to speech")
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.playing, name="Recording article 🎙️"
            ),
        )
        chunked_text = await process_text(article["text"])
        await text_to_speech(f"./articles/{audio_file_name}", chunked_text)

        print("running video conversion")
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.playing, name="Creating video 📼"
            ),
        )
        video_file_name, video_length = await color_clip(f"./articles/{audio_file_name}")
        with open(f"./articles/{text_file_name}", "w") as txt:
            for chunk in chunked_text:
                txt.write(chunk)
        meta = f"By: __{article['author']}__ published: *{article['date']}*"

        print("uploading article to discord")
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.playing, name="Uploading"
            ),
        )

        print(f"upload attempt")
        await upload_message(
            f"> **SUMMARY: {article['title']}**\n> {summary}\n> {meta}\n`length {str(video_length).split('.')[0]}`",
            video_file_name,
            message
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
        # skip domain names
        if not validators.url(url):
            continue
        url_parsed = urlparse(url)
        if url_parsed.netloc not in db:
            db[url_parsed.netloc] = {"whitelist": False, "paywall": False}

            def check(reaction, user):
                return (
                    reply.id == reaction.message.id
                    and user == message.author
                    and (str(reaction.emoji) == "✅" or
                    str(reaction.emoji) == "🚫")
                )

            reply = await message.channel.send(
                f"**{url_parsed.netloc}** not known, react with ✅ to add to whitelist and parse or 🚫 to ignore.",
                reference=message,
            )
            await reply.add_reaction("✅")
            await reply.add_reaction("🚫")
            try:
                reaction, user = await bot.wait_for(
                    "reaction_add", timeout=60.0, check=check
                )
            except TimeoutError:
                await reply.delete()
            else:
                if str(reaction.emoji) == "✅":
                    await reply.delete()
                    db[url_parsed.netloc] = {"whitelist": True, "paywall": False}
                    await process_article(url, message)
                elif str(reaction.emoji) == "🚫":
                    await reply.delete()
            return

        url_profile = db[url_parsed.netloc]
        if url_profile["whitelist"]:
            await process_article(url, message)
            return
        if not url_profile["whitelist"]:
            await message.add_reaction("🚫")
            return


if __name__ == "__main__":
    bot.run(settings.token)  # , log_handler=handler)
