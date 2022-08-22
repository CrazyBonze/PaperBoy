from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer as Summarizer
from sumy.nlp.stemmers import Stemmer
from sumy.utils import get_stop_words
from textwrap import shorten

LANGUAGE = "english"
SENTENCES_COUNT = 5


def summarize(text, sentences=SENTENCES_COUNT, language=LANGUAGE):
    parser = PlaintextParser.from_string(text, Tokenizer(language))
    stemmer = Stemmer(LANGUAGE)

    summarizer = Summarizer(stemmer)
    summarizer.stop_words = get_stop_words(LANGUAGE)

    return shorten(
        " ".join([str(s) for s in summarizer(parser.document, SENTENCES_COUNT)]),
        width=1800,
        placeholder="...",
    )
