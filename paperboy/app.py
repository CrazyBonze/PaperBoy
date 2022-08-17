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
from selenium import webdriver
import chromedriver_autoinstaller
from selenium.webdriver.chrome.options import Options
import google.cloud.texttospeech as tts


def text_to_speech(filename: str, text: str):
    text_input = tts.SynthesisInput(text=text)
    voice_params = tts.VoiceSelectionParams(
        language_code="en-US", name="en-US-Wavenet-I"
    )
    audio_config = tts.AudioConfig(audio_encoding=tts.AudioEncoding.LINEAR16)
    print(audio_config)
    client = tts.TextToSpeechClient()
    response = client.synthesize_speech(
        input=text_input, voice=voice_params, audio_config=audio_config
    )

    #filename = f"{language_code}.wav"
    with open(filename, "wb") as out:
        out.write(response.audio_content)
        print(f'Generated speech saved to "{filename}"')


chromedriver_autoinstaller.install()
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--window-size=1920x1080")


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
        db[url_parsed.netloc] = {"whitelist": True, 'paywall': False}
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

@bot.command(name="paywall", description="Add or remove paywall.")
async def paywall(ctx, url):
    """Turn onn and off paywall diversion."""
    url_parsed = urlparse(url)
    if str(url_parsed.netloc) not in db:
        await ctx.send(f"**{url_parsed.netloc}** not found in database.")
        return
    url_profile = db[url_parsed.netloc]
    url_profile["paywall"] = not url_profile["paywall"]
    db[url_parsed.netloc] = url_profile
    await ctx.send(f"**{url_parsed.netloc}**: {db[url_parsed.netloc]}")

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

def divert_paywall(url):
    url_parsed = urlparse(url)
    url_profile = db[url_parsed.netloc]
    return url_profile["paywall"]

async def process_article(url, message):
    await message.add_reaction("📰")
    await bot.change_presence(
        status=discord.Status.do_not_disturb,
        activity=discord.Activity(
            type=discord.ActivityType.playing, name="busy doing shit"
        ),
    )
    async with message.channel.typing():
        print("downlowding article")
        # Divert paywall
        article = None
        if divert_paywall(url):
            driver = webdriver.Chrome(chrome_options=chrome_options)
            driver.implicitly_wait(10)
            driver.get(f"https://12ft.io/{url}")
            driver.switch_to.frame(driver.find_element("xpath", "//iframe[1]"))
            source = driver.page_source
            driver.quit()
            article = Article('', config=config)
            article.set_html(source)
        else:
            article = Article(url, config=config)
            article.download()

        print("parsing article")
        article.parse()
        print("running nlp on article")
        article.nlp()
        print("running text to speech")
        audio_file_name = f"{slugify(article.title)}.mp3"
        text_file_name = f"{slugify(article.title)}.txt"
        text = "\n".join(wrapper.wrap(article.text))
        #tts = gTTS(text=text, lang="en", slow=False)
        #tts.save(f"./articles/{audio_file_name}")
        text_to_speech(f"./articles/{audio_file_name}", text)
        print("running video conversion")
        video_file_name = color_clip(f"./articles/{audio_file_name}")
        with open(f"./articles/{text_file_name}", 'w') as txt:
            txt.write(text)
        meta = f"By: __{','.join(article.authors or [])}__ {article.publish_date or datetime.min:%Y-%m-%d}\n"
        print("uploading article to discord")
        # check for aiohttp.client_exceptions.ClientOSError
        await message.channel.send(
            f"**SUMMARY: {article.title}**\n{meta}{article.summary[:2000]}",
            #f"**SUMMARY: {title}**\n{meta}{content[:2000]}",
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
            db[url_parsed.netloc] = {"whitelist": False, 'paywall': False}
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
                db[url_parsed.netloc] = {"whitelist": True, 'paywall': False}
                await process_article(url, message)
            return


        url_profile = db[url_parsed.netloc]
        if url_profile["whitelist"]:
            await process_article(url, message)


bot.run(settings.token)  # , log_handler=handler)
