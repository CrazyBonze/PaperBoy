import asyncio
from textwrap import shorten

import pysrt
from sumy.nlp.stemmers import Stemmer
from sumy.nlp.tokenizers import Tokenizer
from sumy.parsers.plaintext import PlaintextParser
from sumy.summarizers.lsa import LsaSummarizer as Summarizer
from sumy.utils import get_stop_words

LANGUAGE = "english"
SENTENCES_COUNT = 5


def _summarize(text, sentences=SENTENCES_COUNT, language=LANGUAGE):
    parser = PlaintextParser.from_string(text, Tokenizer(language))
    stemmer = Stemmer(LANGUAGE)

    summarizer = Summarizer(stemmer)
    summarizer.stop_words = get_stop_words(LANGUAGE)

    return shorten(
        " ".join([str(s) for s in summarizer(parser.document, SENTENCES_COUNT)]),
        width=1800,
        placeholder="...",
    )


async def summarize(text, sentences=SENTENCES_COUNT, language=LANGUAGE):
    loop = asyncio.get_running_loop()
    done = loop.run_in_executor(None, _summarize, text, sentences, language)
    return await done
