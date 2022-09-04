from textwrap import TextWrapper

wrapper = TextWrapper()
wrapper.width = 120
wrapper.fix_sentence_endings = True
wrapper.break_long_words = False
wrapper.break_on_hyphens = False

MAX_CHUNK = 5000

async def process_text(text):
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
