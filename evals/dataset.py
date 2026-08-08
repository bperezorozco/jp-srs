"""jp-srs golden evaluation set. n=20, FROZEN.

Rules this file follows, which hold for any golden set:

  1. It is immutable and versioned. It deliberately does not pull from the
     WaniKani API at run time: if the dataset shifts between runs, the
     numbers stop being comparable and the eval stops being useful.
  2. It is stratified into slices that reflect how the system is actually
     used, not into whatever distribution was convenient to assemble.
  3. It includes deliberate adversarial items, among them one case where
     the system CANNOT satisfy everything it was asked for (an impossible
     level). Watching how the model prioritises there is design
     information, not a broken test case.

Mind the n=20: slices hold 4-5 items each. They support qualitative error
analysis ("do kanji fail differently from vocabulary?"), NOT per-slice
metrics. 3 out of 4 is not 75%.

If you add items, bump DATASET_VERSION and do not compare runs across
different versions.
"""

DATASET_VERSION = "v1"

# slice: core        -> general vocabulary, level anchored to JLPT lists
#        kanji       -> exercises the is_kanji flag (many kanji do not
#                       stand alone as words)
#        adversarial -> cases we already expect to be hard
#        language    -> exercises the translation-language instruction

GOLDEN_SET = [
    # --- core: vocabulary from N5 up to N1 -----------------------
    {"id": "c01", "word": "水",       "level": "N5", "language": "es", "is_kanji": False, "slice": "core"},
    {"id": "c02", "word": "電車",     "level": "N5", "language": "es", "is_kanji": False, "slice": "core"},
    {"id": "c03", "word": "予約",     "level": "N4", "language": "es", "is_kanji": False, "slice": "core"},
    {"id": "c04", "word": "大切",     "level": "N4", "language": "es", "is_kanji": False, "slice": "core"},
    {"id": "c05", "word": "締め切り", "level": "N3", "language": "es", "is_kanji": False, "slice": "core"},
    {"id": "c06", "word": "経験",     "level": "N3", "language": "es", "is_kanji": False, "slice": "core"},
    {"id": "c07", "word": "手続き",   "level": "N2", "language": "es", "is_kanji": False, "slice": "core"},
    {"id": "c08", "word": "措置",     "level": "N1", "language": "es", "is_kanji": False, "slice": "core"},

    # --- kanji: none of these work well as a standalone word ------
    {"id": "k01", "word": "語", "level": "N5", "language": "es", "is_kanji": True, "slice": "kanji"},
    {"id": "k02", "word": "認", "level": "N3", "language": "es", "is_kanji": True, "slice": "kanji"},
    {"id": "k03", "word": "保", "level": "N3", "language": "es", "is_kanji": True, "slice": "kanji"},
    {"id": "k04", "word": "務", "level": "N2", "language": "es", "is_kanji": True, "slice": "kanji"},

    # --- adversarial ---------------------------------------------
    # a01: conflicting constraints. 遵守 is N1 and is requested at N5, so
    #      the system cannot honour both. We want to see whether it keeps
    #      the rest of the sentence simple or drags everything up to N1.
    {"id": "a01", "word": "遵守",     "level": "N5", "language": "es", "is_kanji": False, "slice": "adversarial"},
    # a02: kana-only vocabulary; there is no kanji to put in the furigana.
    {"id": "a02", "word": "ちょっと", "level": "N5", "language": "es", "is_kanji": False, "slice": "adversarial"},
    # a03: kanji with many readings (せい / なま / い-きる / う-まれる).
    #      Exercises furigana_ok harder than any other item.
    {"id": "a03", "word": "生",       "level": "N3", "language": "es", "is_kanji": True,  "slice": "adversarial"},
    # a04: heavily polysemous verb (to hang, to sit, to multiply, to spend...).
    {"id": "a04", "word": "掛ける",   "level": "N3", "language": "es", "is_kanji": False, "slice": "adversarial"},

    # --- language: same task, different translation language ------
    # l02 deliberately repeats 経験/N3 from c06 to isolate the language
    # variable with everything else held constant.
    {"id": "l01", "word": "契約", "level": "N2", "language": "en", "is_kanji": False, "slice": "language"},
    {"id": "l02", "word": "経験", "level": "N3", "language": "it", "is_kanji": False, "slice": "language"},
    {"id": "l03", "word": "確認", "level": "N3", "language": "fr", "is_kanji": False, "slice": "language"},
    {"id": "l04", "word": "説明", "level": "N4", "language": "en", "is_kanji": False, "slice": "language"},
]

SLICES = sorted({item["slice"] for item in GOLDEN_SET})
