"""Evaluation rubric for jp-srs sentence generation.

Two grading layers, cheapest first:

  LAYER 1 - automatic_checks(): deterministic, free, always runs.
      Anything decidable in code must NOT go to a judge. Paying an LLM
      to do the work of an `in` is the single most common eval antipattern.

  LAYER 2/3 - CRITERIA: actual judgement. Labelled first by a human
      (label.py), then by an LLM judge (judge.py). Both read EXACTLY the
      same definition: if the human and the judge are working from
      different rubrics, the agreement between them means nothing.

Criteria are deliberately binary. 1-5 scales do not calibrate, in humans
or in models — everything piles up on 3 and 4.
"""

import re

# Unicode ranges for kanji (CJK ideographs) and kana.
KANJI_RE = re.compile(r"[一-鿿]")
KANA_RE = re.compile(r"[぀-ヿ]")

REQUIRED_FIELDS = ("sentence", "furigana", "translation", "note")

# A label is True, False, None or UNQUALIFIED. None means the annotator
# understood the item and still could not decide, which indicts the
# criterion. UNQUALIFIED means the item sat above the annotator's Japanese
# level, which is a coverage limit and says nothing about the rubric.
# Only True and False ever enter a rate or an agreement calculation.
UNQUALIFIED = "unqualified"

AUTOMATIC_CHECKS = (
    "json_valid",
    "fields_present",
    "sentence_is_japanese",
    "target_present",
    "furigana_is_kana",
    "translation_present",
)


def automatic_checks(item: dict, parsed: dict | None) -> dict[str, bool]:
    """Run the deterministic checks over one parsed output.

    Returns a check -> passed mapping. `parsed` is None when the model did
    not return valid JSON, in which case every check fails.
    """
    if parsed is None:
        return {name: False for name in AUTOMATIC_CHECKS}

    sentence = parsed.get("sentence") or ""
    furigana = parsed.get("furigana") or ""
    translation = parsed.get("translation") or ""

    # For is_kanji items it is enough that the kanji shows up inside some
    # word. For vocabulary the word itself should appear — but verbs and
    # adjectives get conjugated, so we also accept the stem, otherwise
    # 食べる -> 食べます would count as a miss.
    target = item["word"]
    stem = target[:-1] if len(target) > 2 else target
    target_present = target in sentence or stem in sentence

    return {
        "json_valid": True,
        "fields_present": all(field in parsed for field in REQUIRED_FIELDS),
        "sentence_is_japanese": bool(KANA_RE.search(sentence)),
        "target_present": target_present,
        # The furigana field is meant to be the reading: kana, no kanji.
        "furigana_is_kana": bool(furigana) and not KANJI_RE.search(furigana),
        # The translation should not carry Japanese text along with it.
        "translation_present": bool(translation) and not KANA_RE.search(translation),
    }


# ---------------------------------------------------------------
# LAYER 2/3 - judgement criteria
# ---------------------------------------------------------------
# key        -> field name in the stored labels
# short      -> what the human sees in the CLI; must fit on one line
# definition -> the long form, passed verbatim into the judge prompt.
#               If a definition is ambiguous the kappa will come out low,
#               and that is the rubric's fault, not the model's.

CRITERIA = [
    {
        "key": "target_used_correctly",
        "short": "Does it use the target word/kanji with correct meaning and form?",
        "definition": (
            "The sentence uses the target word with a correct meaning and in a "
            "grammatically valid form (conjugation, particles). If the target is "
            "a kanji, the sentence contains a real word that includes it. Answer "
            "NO if the word feels shoehorned in, carries the wrong sense, or is "
            "conjugated incorrectly."
        ),
    },
    {
        "key": "level_ok",
        "short": "Is the vocabulary and grammar within the requested JLPT level (or easier)?",
        "definition": (
            "All vocabulary and grammar in the sentence sit at the requested JLPT "
            "level or below. The target word itself does NOT count towards this "
            "judgement — the user picked it, so it may be harder than the level. "
            "Answer NO if the rest of the sentence pulls in vocabulary or grammar "
            "from a harder level than the one requested."
        ),
    },
    {
        "key": "furigana_ok",
        "short": "Does the furigana match the sentence, with correct readings?",
        "definition": (
            "The furigana field is the same sentence transcribed into kana, with "
            "nothing dropped or added, and every reading is the correct one for "
            "that kanji in that context. Pay particular attention to kanji with "
            "multiple readings."
        ),
    },
    {
        "key": "translation_ok",
        "short": "Is the translation faithful AND in the requested language?",
        "definition": (
            "The translation conveys the meaning of the Japanese sentence without "
            "dropping or inventing information, and is written in the language "
            "that was requested. Answer NO if it is in a different language, even "
            "if the translation itself is good."
        ),
    },
    {
        "key": "natural",
        "short": "Does it sound natural — something a Japanese speaker would say?",
        "definition": (
            "The sentence sounds natural in Japanese, casual or formal as "
            "appropriate; it does not read as a contrived example built around "
            "the target word. Answer NO if it is grammatically correct but nobody "
            "would actually phrase it that way."
        ),
    },
    {
        "key": "note_ok",
        "short": "Is the note correct and useful (or reasonably null)?",
        "definition": (
            "The note field carries correct, useful information about usage or a "
            "grammatical nuance, or is null when there is genuinely nothing worth "
            "flagging. Answer NO if the note is wrong, trivial ('this word means "
            "X'), or null when there was something relevant to explain."
        ),
    },
]

CRITERIA_KEYS = [criterion["key"] for criterion in CRITERIA]
