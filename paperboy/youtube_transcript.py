import asyncio
from urllib.parse import parse_qs, urlparse

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter


def get_youtube_video_id(url):
    parsed_url = urlparse(url)
    if parsed_url.netloc == "youtu.be":
        return parsed_url.path[1:]
    if parsed_url.netloc in ("www.youtube.com", "youtube.com"):
        if parsed_url.path == "/watch":
            parsed_qs = parse_qs(parsed_url.query)
            return parsed_qs.get("v", [None])[0]
        elif parsed_url.path[:7] == "/embed/":
            return parsed_url.path.split("/")[2]
        elif parsed_url.path[:3] == "/v/":
            return parsed_url.path.split("/")[2]
    return None


def fetch_transcript(video_id):
    formatter = TextFormatter()
    transcript = YouTubeTranscriptApi.get_transcript(video_id)
    return formatter.format_transcript(transcript=transcript)


async def get_transcript(video_id):
    loop = asyncio.get_running_loop()
    done = loop.run_in_executor(None, fetch_transcript, video_id)
    return await done
