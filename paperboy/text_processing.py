import textwrap
from datetime import datetime

MAX_CHUNK = 4900


async def process_text(text):
    wrapper = textwrap.TextWrapper()
    wrapper.width = 120
    wrapper.fix_sentence_endings = True
    wrapper.break_long_words = False
    wrapper.break_on_hyphens = False
    formatted = []
    for t in text.split("\n"):
        formatted.append("\n".join(wrapper.wrap(t)))

    chunked = [""]
    for f in formatted:
        if len(chunked[-1]) + len(f"{f}\n") < MAX_CHUNK:
            chunked[-1] = chunked[-1] + f"{f}\n"
        else:
            chunked.append(f)
    return chunked


async def format_article(title, text, author=None, date=datetime.min, width=120):
    wrapper = textwrap.TextWrapper(width=width)
    wrapper.initial_indent = ""  # Adding an asterisk as initial indent for the title
    wrapper.subsequent_indent = ""  # Subsequent lines will be indented by two spaces
    wrapper.expand_tabs = False  # Expand tabs to spaces
    wrapper.replace_whitespace = False  # Preserve the original whitespaces
    wrapper.break_long_words = False  # Don't break words that are longer than 'width'
    wrapper.break_on_hyphens = True  # Don't break words at hyphens

    # Wrap title, text, and metadata individually
    wrapped_title = wrapper.fill(title)
    wrapped_text = wrapper.fill(text)
    wrapped_author = wrapper.fill(f"By: {author}")
    wrapped_date = wrapper.fill(f"Published: {date}")

    # Combine them together
    formatted_article = (
        f"{wrapped_title}\n\n{wrapped_text}\n\n{wrapped_author}\n{wrapped_date}"
    )

    return formatted_article
