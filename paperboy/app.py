import asyncio
import tempfile
import time
from asyncio import TimeoutError
from datetime import datetime, timedelta
from itertools import cycle
from pathlib import Path
from urllib.parse import urlparse

import backoff
import discord
import google.cloud.texttospeech as tts
import nltk
import pytube
import trafilatura
import validators
from aiohttp.client_exceptions import ClientOSError
from courlan import check_url
from discord.ext import commands, tasks
from dotenv import load_dotenv
from gtts import gTTS
from moviepy.editor import AudioFileClip, ColorClip, ImageClip, concatenate_audioclips
from pydantic import BaseSettings
from selenium import webdriver

# import chromedriver_autoinstaller
from selenium.webdriver.chrome.options import Options
from slugify import slugify
from sqlitedict import SqliteDict
from summerizer import summarize
from text_processing import format_article, process_text
from urlextract import URLExtract
from youtube_transcript import get_transcript, get_youtube_video_id

directory = Path("./articles")
directory.mkdir(parents=True, exist_ok=True)
nltk.download("punkt")
load_dotenv()

# os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/home/michael/PaperBoy/key.json"
SELENIUM_URL = "http://selenium:4444/wd/hub"
SELENIUM_URL = "http://localhost:4444/wd/hub"


async def write_audio_to_tempfile(i, text, tmp_dir, voice_params, audio_config, client):
    text_input = tts.SynthesisInput(text=text)
    response = await client.synthesize_speech(
        input=text_input, voice=voice_params, audio_config=audio_config
    )
    tmp_audio_path = Path(tmp_dir) / f"{i}.mp3"
    with tmp_audio_path.open("wb") as out:
        out.write(response.audio_content)
    return AudioFileClip(str(tmp_audio_path))


async def text_to_speech(filename: str, chunked_text: [str]):
    voice_params = tts.VoiceSelectionParams(
        language_code="en-US", name="en-US-Wavenet-I"
    )
    audio_config = tts.AudioConfig(audio_encoding=tts.AudioEncoding.LINEAR16)
    client = tts.TextToSpeechAsyncClient()

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_audio_clips = await asyncio.gather(
            *[
                write_audio_to_tempfile(
                    i, text, tmp_dir, voice_params, audio_config, client
                )
                for i, text in enumerate(chunked_text)
            ]
        )
        concat_clip = concatenate_audioclips(tmp_audio_clips)
        concat_clip.write_audiofile(filename)


# chromedriver_autoinstaller.install()
chrome_options = Options()
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-gpu")
# chrome_options.add_argument("--headless")
chrome_options.add_argument("--window-size=1920x1080")
chrome_options.add_argument("--ignore-ssl-errors=yes")
chrome_options.add_argument("--ignore-certificate-errors")
chrome_options.add_argument("--user-data-dir=/tmp/chrome")


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


async def send_paged_message(ctx, content_list, page_size=20):
    pages = [
        content_list[i : i + page_size] for i in range(0, len(content_list), page_size)
    ]
    for i, page in enumerate(pages):
        if len(pages) > 1:
            page_content = f"**Page {i + 1} of {len(pages)}**\n"
        else:
            page_content = ""
        page_content += "```" + "".join(page) + "```"
        await ctx.send(page_content)
        await asyncio.sleep(0.25)


def build_table(db):
    max_domain_length = max(len(netloc) for netloc in db.keys())
    spacing = max(20, max_domain_length + 2)  # 2 extra spaces for padding

    header = "{:<{spacing}} {:<10} {:<10} {:<10}\n".format(
        "Domain", "Count", "Enabled", "Paywall", spacing=spacing
    )
    separator = (
        "-" * (spacing + 33) + "\n"
    )  # 33 = 10 for "Count" + 10 for "Enabled" + 10 for "Paywall" + 3 for spaces

    content_list = [header, separator]

    for netloc, value in db.items():
        count = value.get("count", 0)
        enabled = "✅" if value["whitelist"] else "❌"
        paywall = "✅" if value["paywall"] else "❌"
        line = "{:<{spacing}} {:<10} {:<10} {:<10}\n".format(
            netloc, count, enabled, paywall, spacing=spacing
        )
        content_list.append(line)
    return content_list


@_list.command(name="all")
async def all(ctx):
    """List all domains in the database"""
    content_list = build_table(db)
    await send_paged_message(ctx, content_list)


@_list.command(name="add")
async def add(ctx, url):
    """Add a domain to the whitelist"""
    url_parsed = urlparse(url)
    domain = str(url_parsed.netloc) or url
    if validators.domain(domain) is not True:
        await ctx.send(
            f"❗ **Invalid Domain:** Couldn't find a valid domain in `{url}`."
        )
        return

    if domain not in db:
        db[domain] = {"whitelist": True, "paywall": False, "count": 0}
        single_entry_db = {domain: db[domain]}
        content_list = build_table(single_entry_db)
        msg = f"**New Entry Added:**\n```"
        msg += "".join(content_list)
        msg += "```"
        await ctx.send(msg)
        return
    await ctx.send(
        f"🛑 **Domain Already Exists:** `{domain}` is already in the database."
    )


@_list.command(name="rm")
async def rm(ctx, url):
    """Remove a domain from the whitelist"""
    url_parsed = urlparse(url)
    domain = str(url_parsed.netloc) or url

    if domain not in db:
        await ctx.send(f"❗ **Domain Not Found:** `{domain}` is not in the database.")
        return

    del db[domain]

    msg = f"🗑️ **Domain Removed:** `{domain}` has been removed from the database."
    await ctx.send(msg)


@bot.command(name="paywall", description="Add or remove paywall.")
async def paywall(ctx, url):
    """Turn on and off paywall diversion."""
    url_parsed = urlparse(url)
    domain = str(url_parsed.netloc) or url

    if domain not in db:
        await ctx.send(f"❗ **Domain Not Found:** `{domain}` is not in the database.")
        return

    url_profile = db[domain]
    url_profile["paywall"] = not url_profile["paywall"]
    db[domain] = url_profile

    single_entry_db = {domain: db[domain]}
    content_list = build_table(single_entry_db)
    msg = f"🔄 **Paywall Toggled for:** `{domain}`\n```"
    msg += "".join(content_list)
    msg += "```"

    await ctx.send(msg)


@bot.command(name="whitelist", description="Add or remove whitelist.")
async def whitelist(ctx, url):
    """Add or remove a domain from the whitelist."""
    url_parsed = urlparse(url)
    domain = str(url_parsed.netloc) or url

    if domain not in db:
        await ctx.send(f"❗ **Domain Not Found:** `{domain}` is not in the database.")
        return

    url_profile = db[domain]
    url_profile["whitelist"] = not url_profile["whitelist"]
    db[domain] = url_profile

    single_entry_db = {domain: db[domain]}
    content_list = build_table(single_entry_db)
    msg = f"🔄 **Whitelist Toggled for:** `{domain}`\n```"
    msg += "".join(content_list)
    msg += "```"

    await ctx.send(msg)


@bot.command(name="ping", description="Check response.")
async def ping(ctx, num_trials: int = 5):
    """Measure the ping between Discord and the bot"""
    if num_trials <= 0 or num_trials > 20:  # Feel free to adjust the upper limit
        await ctx.send(
            "❗ **Invalid Input:** Number of trials must be between 1 and 20."
        )
        return
    print("ping pong")

    # Set the header
    header = f"🏓 **Ping Diagnostics:**\n"

    # Mimic the terminal ping command look
    bot_name = bot.user.name
    msg = f"{ctx.author}@{ctx.guild}:~$ ping {bot_name}\n"

    # Combine the header and the initial message
    full_msg = header + f"```{msg}```"

    # Send initial message
    message = await ctx.send(full_msg)

    # Measure command response latency
    latency_list = []
    for i in range(num_trials):
        t1 = time.perf_counter()
        async with ctx.typing():
            t2 = time.perf_counter()
        latency = round((t2 - t1) * 1000)
        latency_list.append(latency)

        msg += f"Ping attempt {i+1}: {latency} ms\n"

        # Edit the message to add new line
        full_msg = header + f"```{msg}```"
        await message.edit(content=full_msg)

        await asyncio.sleep(1)  # Add delay between pings

    avg_latency = round(sum(latency_list) / len(latency_list))
    max_latency = max(latency_list)
    min_latency = min(latency_list)
    msg += f"--- {bot_name} ping statistics ---\n"
    msg += f"{num_trials} messages transmitted, time {sum(latency_list)}ms\n"
    msg += f"rtt min/avg/max = {min_latency}/{avg_latency}/{max_latency} ms\n"

    # Edit the message to add final statistics
    full_msg = header + f"```{msg}```"
    await message.edit(content=full_msg)


@bot.event
async def on_ready():
    for guild in bot.guilds:
        if guild.id == settings.guild:
            break
    changeStatus.start()
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
        videoclip.write_videofile(
            filename,
            fps=1,
            audio_bitrate="84k",
            threads=8,
        )
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
            driver.get(url)
            source = driver.page_source
            driver.quit()
        else:
            source = trafilatura.fetch_url(url)
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
    print(
        "Backing off {wait:0.1f} seconds after {tries} tries "
        "calling function {target} with args {args} and kwargs "
        "{kwargs}".format(**details)
    )


@backoff.on_exception(
    backoff.constant, ClientOSError, max_tries=3, interval=1, on_backoff=backoff_hdlr
)
async def upload_message(text, video_file_name, text_file_name, reference):
    await reference.channel.send(
        text,
        files=[
            discord.File(video_file_name),
            discord.File(text_file_name),
        ],
        reference=reference,
    )


async def process_youtube(url, message):
    await message.add_reaction("📰")
    async with message.channel.typing():
        video_id = get_youtube_video_id(url)
        text_file_name = f"./articles/{video_id}.txt"
        transcript = await get_transcript(video_id)
        summary = await summarize(transcript)
        yt_video = pytube.YouTube(url=url)
        with open(text_file_name, "w") as txt:
            author = f"By: {yt_video.author}"
            date = f"Published: {yt_video.publish_date}"
            txt.write(f"{yt_video.title}\n\n{transcript}\n{author}\n{date}")
        await message.channel.send(
            f"> **SUMMARY: {yt_video.title}**\n> {summary}\n{author} {date}",
            files=[discord.File(text_file_name)],
            reference=message,
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

        print("running text to speech")
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.playing, name="Recording article 🎙️"
            ),
        )
        chunked_text = await process_text(article["text"])
        article_file_name = f"./articles/{text_file_name}"
        with open(article_file_name, "w") as txt:
            txt.write(await format_article(article=article, width=120))
        await text_to_speech(f"./articles/{audio_file_name}", chunked_text)

        print("running video conversion")
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.playing, name="Creating video 📼"
            ),
        )
        video_file_name, video_length = await color_clip(
            f"./articles/{audio_file_name}"
        )
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
            article_file_name,
            message,
        )
        print("finished")


async def handle_unknown_domain(url_parsed, message):
    # Your logic for handling unknown domains
    db[url_parsed.netloc] = {"whitelist": False, "paywall": False, "count": 0}

    def check(reaction, user):
        return (
            reply.id == reaction.message.id
            and user == message.author
            and (str(reaction.emoji) == "✅" or str(reaction.emoji) == "🚫")
        )

    reply = await message.channel.send(
        f"**{url_parsed.netloc}** not known, react with ✅ to add to whitelist and parse or 🚫 to ignore.",
        reference=message,
    )
    await reply.add_reaction("✅")
    await reply.add_reaction("🚫")
    try:
        reaction, user = await bot.wait_for("reaction_add", timeout=60.0, check=check)
    except TimeoutError:
        await reply.delete()
    else:
        if str(reaction.emoji) == "✅":
            await reply.delete()
            db[url_parsed.netloc] = {
                "whitelist": True,
                "paywall": False,
                "count": 1,
            }
            await process_article(str(url_parsed.geturl()), message)
        elif str(reaction.emoji) == "🚫":
            await reply.delete()
    return


async def handle_known_domain(url_parsed, message):
    # Your logic for handling known domains
    url_profile = db[url_parsed.netloc]

    url = str(url_parsed.geturl())
    if url_profile["whitelist"]:
        if url_parsed.netloc in [
            "www.youtube.com",
            "youtube.com",
            "www.youtu.be",
            "youtu.be",
        ]:
            await process_youtube(url, message)
        else:
            await process_article(url, message)
        url_profile["count"] = url_profile.get("count", 0) + 1
        db[url_parsed.netloc] = url_profile
        return
    if not url_profile["whitelist"]:
        await message.add_reaction("🚫")
        return


@bot.event
async def on_message(message):
    if message.channel.id not in settings.channels:
        return
    if message.author == bot.user:
        return

    username = str(message.author).split("#")[0]
    channel = message.channel.name
    user_message = str(message.content)

    if user_message.startswith("$"):
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
            await handle_unknown_domain(url_parsed, message)
        else:
            await handle_known_domain(url_parsed, message)


if __name__ == "__main__":
    print("Running bot")
    bot.run(settings.token)  # , log_handler=handler)
