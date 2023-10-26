import asyncio
import io
import re
import tempfile
from textwrap import wrap
from typing import Iterator
from urllib.parse import parse_qs, urlparse

import pytube
import whisper
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter

# Load Whisper model
model = whisper.load_model("small.en")


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


def format_timestamp(
    seconds: float, always_include_hours: bool = False, decimal_marker: str = "."
):
    assert seconds >= 0, "non-negative timestamp expected"
    milliseconds = round(seconds * 1000.0)

    hours = milliseconds // 3_600_000
    milliseconds -= hours * 3_600_000

    minutes = milliseconds // 60_000
    milliseconds -= minutes * 60_000

    seconds = milliseconds // 1_000
    milliseconds -= seconds * 1_000

    hours_marker = f"{hours:02d}:" if always_include_hours or hours > 0 else ""
    return (
        f"{hours_marker}{minutes:02d}:{seconds:02d}{decimal_marker}{milliseconds:03d}"
    )


def break_line(line: str, length: int):
    return "\n".join(wrap(line, length))


def process_segment(segment: dict, line_length: int = 0):
    segment["text"] = segment["text"].strip()
    if line_length > 0 and len(segment["text"]) > line_length:
        # break at N characters as per Netflix guidelines
        segment["text"] = break_line(segment["text"], line_length)

    return segment


def generate_srt(transcript: Iterator[dict], line_length: int = 80) -> str:
    srt_content = ""
    for i, segment in enumerate(transcript, start=1):
        segment = process_segment(segment, line_length=line_length)
        srt_segment = (
            f"\n{i}\n"
            f"{format_timestamp(segment['start'], always_include_hours=True, decimal_marker=',')} --> "
            f"{format_timestamp(segment['end'], always_include_hours=True, decimal_marker=',')}\n"
            f"{segment['text'].strip().replace('-->', '->')}\n"
        )
        srt_content += srt_segment

    return srt_content


async def youtube_to_text(url):
    # Create a temporary file
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=True) as temp_audio:
        # Initialize a YouTube object
        youtube = pytube.YouTube(url)

        # Get the audio stream
        audio_stream = youtube.streams.filter(only_audio=True).first()

        # Download the audio stream to temporary file
        audio_stream.download(filename=temp_audio.name)

        # Transcribe audio file asynchronously
        result = await asyncio.to_thread(model.transcribe, audio=temp_audio.name)
        # Return transcript text
        return {
            # "srt": generate_srt([s._asdict() for s in result]),
            # "text": " ".join([s.text for s in result]),
            "srt": generate_srt(result["segments"]),
            "text": result["text"],
        }
        # return result["text"]


async def get_transcript(video_id):
    loop = asyncio.get_running_loop()
    done = loop.run_in_executor(None, fetch_transcript, video_id)
    return await done
