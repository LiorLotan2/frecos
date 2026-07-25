"""Minimal wikitext-to-plain-text conversion, just enough to find the sentence
holding a SQuAD answer string across revisions. Not a full wikitext parser.
"""
import re

REF_RE = re.compile(r"<ref[^>]*>.*?</ref>|<ref[^>]*/>", re.DOTALL)
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
TEMPLATE_RE = re.compile(r"\{\{[^{}]*\}\}")
TABLE_RE = re.compile(r"\{\|.*?\|\}", re.DOTALL)
LINK_PIPED_RE = re.compile(r"\[\[[^\]|]*\|([^\]]*)\]\]")
LINK_PLAIN_RE = re.compile(r"\[\[([^\]]*)\]\]")
BOLD_ITALIC_RE = re.compile(r"'{2,5}")
HEADING_RE = re.compile(r"^=+\s*(.*?)\s*=+$", re.MULTILINE)
TAG_RE = re.compile(r"<[^>]+>")


def to_plain_text(wikitext):
    text = wikitext
    for _ in range(3):
        text = TEMPLATE_RE.sub("", text)
    text = TABLE_RE.sub("", text)
    text = COMMENT_RE.sub("", text)
    text = REF_RE.sub("", text)
    text = LINK_PIPED_RE.sub(r"\1", text)
    text = LINK_PLAIN_RE.sub(r"\1", text)
    text = BOLD_ITALIC_RE.sub("", text)
    text = TAG_RE.sub("", text)
    text = HEADING_RE.sub(r"\1.", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def split_sentences(text):
    return re.split(r"(?<=[.!?])\s+", text)


def find_answer_sentence(wikitext, answer):
    plain = to_plain_text(wikitext)
    answer_lower = answer.lower()
    for sentence in split_sentences(plain):
        if answer_lower in sentence.lower():
            return sentence.strip()
    return None
