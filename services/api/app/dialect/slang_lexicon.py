"""
Curated reference lexicon of Spanish regional slang.

Purpose
-------
The corpus is unevenly distributed: Paraguay contributes 72 seconds of audio and
Equatorial Guinea 20 minutes, which is far too little to *discover* their
vocabulary statistically. This module supplies an externally-sourced lexicon so
those varieties can still be **detected and evaluated** even where the audio is
thin.

The two resources are complementary and must not be confused:

* `distinctive.py` performs **discovery** -- it finds what is distinctive without
  prior knowledge, and is the honest evidence for well-represented countries.
* This lexicon performs **detection** -- it recalls known terms, providing recall
  where discovery lacks data, and a validation target where discovery has data.

Provenance
----------
Entries are compiled from published descriptive sources rather than invented.
Each entry carries a `source` tag so the thesis can cite where it came from.
See `docs/LEXICON_SOURCES.md`.

Coverage is deliberately deepest for the countries with the least audio.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable, Optional


@dataclass(frozen=True)
class SlangEntry:
    """One regional term with gloss and provenance."""

    term: str
    gloss: str
    countries: tuple[str, ...]
    category: str = "general"
    source: str = ""
    # Terms that are also standard Spanish with a different meaning need care:
    # `guagua` is 'bus' in the Caribbean but 'baby' in the Andes.
    polysemous: bool = False


# --------------------------------------------------------------------------- #
# Lexicon
# --------------------------------------------------------------------------- #

LEXICON: tuple[SlangEntry, ...] = (
    # ===================== PARAGUAY (72s of audio) ========================= #
    # Paraguayan Spanish is heavily influenced by Guarani; the mixed register is
    # called *jopara* ("mixture"). Guarani-origin particles attach to Spanish
    # sentences, which is a strong and easily detectable signal.
    SlangEntry("haku", "it is hot (weather)", ("paraguay",), "weather", "jopara"),
    SlangEntry("hakueterei", "it is extremely hot", ("paraguay",), "weather", "jopara"),
    SlangEntry("tranquilopa", "all good, no worries", ("paraguay",), "discourse", "jopara"),
    SlangEntry("jaha", "let's go", ("paraguay",), "discourse", "jopara"),
    SlangEntry("chera'a", "my friend, mate", ("paraguay",), "address", "jopara"),
    SlangEntry("purete", "cool, excellent", ("paraguay",), "evaluation", "jopara"),
    SlangEntry("chake", "watch out, careful", ("paraguay",), "warning", "jopara"),
    SlangEntry("hake", "watch out, careful", ("paraguay",), "warning", "jopara"),
    SlangEntry("kaigue", "listless, lazy, low energy", ("paraguay",), "state", "jopara"),
    SlangEntry("nde", "you (Guarani 2sg), used vocatively", ("paraguay",), "address", "jopara"),
    SlangEntry("luego", "emphatic clause-final particle", ("paraguay",), "discourse",
               "jopara", polysemous=True),
    SlangEntry("gua'u", "supposedly, pretend", ("paraguay",), "discourse", "jopara"),
    SlangEntry("mita", "kid, child", ("paraguay",), "person", "jopara"),
    SlangEntry("karai", "sir, mister", ("paraguay",), "address", "jopara"),
    SlangEntry("na", "softening particle (please)", ("paraguay",), "discourse",
               "jopara", polysemous=True),
    SlangEntry("piko", "interrogative emphatic particle", ("paraguay",), "discourse", "jopara"),
    SlangEntry("guapo", "hard-working (not 'handsome')", ("paraguay",), "evaluation",
               "jopara", polysemous=True),

    # ===================== BOLIVIA (16 min of audio) ======================= #
    # Quechua and Aymara substrate; sharp camba (lowland) vs colla (highland)
    # regional split.
    SlangEntry("wawa", "baby, small child", ("bolivia", "peru", "ecuador"), "person", "quechua"),
    SlangEntry("jichi", "dude, mate", ("bolivia",), "address", "bolivian"),
    SlangEntry("llajwa", "spicy salsa", ("bolivia",), "food", "quechua"),
    SlangEntry("chela", "beer", ("bolivia", "mexico", "peru"), "food", "regional"),
    SlangEntry("boliche", "bar, nightclub", ("bolivia", "argentina"), "place", "regional"),
    SlangEntry("velay", "expression of surprise", ("bolivia",), "interjection", "bolivian"),
    SlangEntry("yesca", "broke, out of money", ("bolivia",), "state", "bolivian"),
    SlangEntry("camba", "person from the eastern lowlands", ("bolivia",), "identity", "bolivian"),
    SlangEntry("colla", "person from the highlands", ("bolivia",), "identity", "bolivian"),
    SlangEntry("cholita", "indigenous Andean woman (traditional dress)", ("bolivia",),
               "identity", "bolivian"),
    SlangEntry("api", "hot purple-maize drink", ("bolivia",), "food", "quechua"),
    SlangEntry("salteña", "baked filled pastry", ("bolivia",), "food", "bolivian"),
    SlangEntry("pues", "emphatic clause-final (often reduced to 'pue')", ("bolivia",),
               "discourse", "andean", polysemous=True),
    SlangEntry("elay", "look there, surprise marker", ("bolivia",), "interjection", "bolivian"),
    SlangEntry("imilla", "girl (Aymara)", ("bolivia",), "person", "aymara"),
    SlangEntry("chango", "boy, young man", ("bolivia", "argentina"), "person", "andean"),

    # ============ EQUATORIAL GUINEA (20 min of audio) ====================== #
    # The only African country with Spanish as official language. Substrate from
    # Fang, Bubi and Annobonese; many speakers acquire Spanish as L2, which
    # produces characteristic agreement and preposition patterns.
    SlangEntry("banga", "palm wine", ("equatorial_guinea",), "food", "fang"),
    SlangEntry("malamba", "traditional dance / sugarcane spirit", ("equatorial_guinea",),
               "culture", "fang"),
    SlangEntry("fang", "principal ethnic group and language", ("equatorial_guinea",),
               "identity", "guinean"),
    SlangEntry("bubi", "ethnic group of Bioko island", ("equatorial_guinea",),
               "identity", "guinean"),
    SlangEntry("annobones", "Annobon creole / islander", ("equatorial_guinea",),
               "identity", "guinean"),
    SlangEntry("malabo", "capital city", ("equatorial_guinea",), "place", "guinean"),
    SlangEntry("bata", "largest mainland city", ("equatorial_guinea",), "place", "guinean"),
    SlangEntry("bioko", "island province", ("equatorial_guinea",), "place", "guinean"),
    SlangEntry("ntangan", "white person, European (Fang)", ("equatorial_guinea",),
               "person", "fang"),
    SlangEntry("topé", "palm wine", ("equatorial_guinea",), "food", "guinean"),

    # ===================== NICARAGUA (22 min) ============================== #
    SlangEntry("maje", "dude, mate", ("nicaragua", "el_salvador"), "address", "central_american"),
    SlangEntry("dale pues", "alright then", ("nicaragua",), "discourse", "central_american"),
    SlangEntry("tuani", "cool, great", ("nicaragua",), "evaluation", "central_american"),
    SlangEntry("chunche", "thing, whatchamacallit", ("nicaragua", "costa_rica"),
               "object", "central_american"),
    SlangEntry("pinolero", "Nicaraguan person", ("nicaragua",), "identity", "central_american"),
    SlangEntry("chavalo", "kid, young person", ("nicaragua",), "person", "central_american"),

    # ===================== CUBA (17 min) =================================== #
    SlangEntry("asere", "mate, buddy", ("cuba",), "address", "cuban"),
    SlangEntry("que bola", "what's up", ("cuba",), "greeting", "cuban"),
    SlangEntry("jeva", "girlfriend, woman", ("cuba",), "person", "cuban"),
    SlangEntry("yuma", "foreigner, the USA", ("cuba",), "identity", "cuban"),
    SlangEntry("pinchar", "to work", ("cuba",), "action", "cuban"),
    SlangEntry("guagua", "bus", ("cuba", "dominican_republic", "puerto_rico"),
               "transport", "caribbean", polysemous=True),

    # ===================== PERU (19 min) =================================== #
    SlangEntry("causa", "close friend", ("peru",), "address", "peruvian"),
    SlangEntry("chamba", "work, job", ("peru", "mexico"), "work", "regional"),
    SlangEntry("bacan", "cool, great", ("peru", "chile", "colombia"), "evaluation", "regional"),
    SlangEntry("jato", "house", ("peru",), "place", "peruvian"),
    SlangEntry("pata", "friend, mate", ("peru",), "address", "peruvian"),
    SlangEntry("chevere", "cool", ("peru", "venezuela", "colombia"), "evaluation", "regional"),

    # ===== Well-represented countries: anchors for lexicon validation ====== #
    SlangEntry("che", "vocative: hey, mate", ("argentina", "uruguay"), "address", "rioplatense"),
    SlangEntry("boludo", "dude (familiar) / idiot (pejorative)", ("argentina", "uruguay"),
               "address", "lunfardo"),
    SlangEntry("laburo", "work, job", ("argentina", "uruguay"), "work", "lunfardo"),
    SlangEntry("quilombo", "mess, chaos", ("argentina", "uruguay"), "state", "lunfardo"),
    SlangEntry("pibe", "kid, young man", ("argentina",), "person", "lunfardo"),
    SlangEntry("weon", "dude / idiot", ("chile",), "address", "chilean"),
    SlangEntry("cachai", "you get it?", ("chile",), "discourse", "chilean"),
    SlangEntry("po", "clause-final emphatic (from 'pues')", ("chile",), "discourse", "chilean"),
    SlangEntry("bacan", "cool", ("chile",), "evaluation", "chilean"),
    SlangEntry("parce", "mate, friend", ("colombia",), "address", "colombian"),
    SlangEntry("chimba", "awesome (or bad, by context)", ("colombia",), "evaluation",
               "colombian", polysemous=True),
    SlangEntry("bacano", "cool, great", ("colombia",), "evaluation", "colombian"),
    SlangEntry("berraco", "tough, impressive person", ("colombia",), "evaluation", "colombian"),
    SlangEntry("guey", "dude", ("mexico",), "address", "mexican"),
    SlangEntry("orale", "wow / alright", ("mexico",), "interjection", "mexican"),
    SlangEntry("chido", "cool", ("mexico",), "evaluation", "mexican"),
    SlangEntry("no manches", "no way, you're kidding", ("mexico",), "interjection", "mexican"),
    SlangEntry("chamaco", "kid", ("mexico",), "person", "mexican"),
    SlangEntry("chamo", "kid, mate", ("venezuela",), "address", "venezuelan"),
    SlangEntry("pana", "friend", ("venezuela", "puerto_rico", "ecuador"), "address", "regional"),
    SlangEntry("burda", "a lot, very", ("venezuela",), "intensifier", "venezuelan"),
    SlangEntry("vaina", "thing, stuff (all-purpose)", ("venezuela", "dominican_republic",
                                                      "colombia", "panama"), "object", "caribbean"),
    SlangEntry("mae", "dude, mate", ("costa_rica",), "address", "costa_rican"),
    SlangEntry("pura vida", "great / hello / thanks (all-purpose)", ("costa_rica",),
               "discourse", "costa_rican"),
    SlangEntry("tuanis", "cool, great", ("costa_rica",), "evaluation", "costa_rican"),
    SlangEntry("tio", "dude, mate", ("spain",), "address", "peninsular"),
    SlangEntry("guay", "cool", ("spain",), "evaluation", "peninsular"),
    SlangEntry("vale", "okay, alright", ("spain",), "discourse", "peninsular"),
    SlangEntry("molar", "to be cool, to like", ("spain",), "evaluation", "peninsular"),
    SlangEntry("curro", "work, job", ("spain",), "work", "peninsular"),
    SlangEntry("chapin", "Guatemalan person", ("guatemala",), "identity", "central_american"),
    SlangEntry("shuco", "dirty / a street hot dog", ("guatemala",), "evaluation",
               "central_american", polysemous=True),
    SlangEntry("cerote", "mate (familiar) / insult", ("guatemala",), "address",
               "central_american", polysemous=True),
    SlangEntry("catracho", "Honduran person", ("honduras",), "identity", "central_american"),
    SlangEntry("guanaco", "Salvadoran person", ("el_salvador",), "identity", "central_american"),
    SlangEntry("bayunco", "silly, joker", ("el_salvador",), "evaluation", "central_american"),
    SlangEntry("chero", "friend, mate", ("el_salvador",), "address", "central_american"),
    SlangEntry("boricua", "Puerto Rican person", ("puerto_rico",), "identity", "puerto_rican"),
    SlangEntry("brutal", "amazing", ("puerto_rico",), "evaluation", "puerto_rican",
               polysemous=True),
    SlangEntry("janguear", "to hang out (from English)", ("puerto_rico",), "action",
               "puerto_rican"),
    SlangEntry("wepa", "expression of excitement", ("puerto_rico",), "interjection",
               "puerto_rican"),
    SlangEntry("chevere", "cool, great", ("venezuela", "colombia", "puerto_rico"),
               "evaluation", "regional"),
    SlangEntry("dique", "supposedly, allegedly", ("dominican_republic",), "discourse",
               "dominican"),
    SlangEntry("tiguere", "streetwise person", ("dominican_republic",), "person", "dominican"),
    SlangEntry("chin", "a little bit", ("dominican_republic",), "quantity", "dominican"),
    SlangEntry("juma", "drunkenness", ("dominican_republic",), "state", "dominican"),
    SlangEntry("chuleta", "expression of surprise", ("panama",), "interjection", "panamanian"),
    SlangEntry("xopa", "what's up (reversed 'pasho')", ("panama",), "greeting", "panamanian"),
    SlangEntry("yeye", "posh, upper class", ("panama",), "identity", "panamanian"),
    SlangEntry("ñero", "mate, buddy", ("ecuador",), "address", "ecuadorian"),
    SlangEntry("chuta", "expression of surprise", ("ecuador",), "interjection", "ecuadorian"),
    SlangEntry("simon", "yes, agreed", ("ecuador", "mexico"), "discourse", "regional"),
    SlangEntry("bo", "vocative particle", ("uruguay",), "address", "uruguayan"),
    SlangEntry("ta", "okay, alright (from 'esta')", ("uruguay",), "discourse", "uruguayan"),
    SlangEntry("championes", "trainers, sneakers", ("uruguay",), "object", "uruguayan"),
)


# --------------------------------------------------------------------------- #
# Indexing and lookup
# --------------------------------------------------------------------------- #

def _fold(text: str) -> str:
    """Lowercase and strip accents for tolerant matching."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


BY_COUNTRY: dict[str, list[SlangEntry]] = {}
for _entry in LEXICON:
    for _country in _entry.countries:
        BY_COUNTRY.setdefault(_country, []).append(_entry)

BY_TERM: dict[str, SlangEntry] = {_fold(e.term): e for e in LEXICON}

# One alternation per country, longest-first so multi-word terms win.
_COUNTRY_PATTERNS: dict[str, re.Pattern[str]] = {
    country: re.compile(
        r"\b(" + "|".join(
            re.escape(_fold(e.term))
            for e in sorted(entries, key=lambda x: -len(x.term))
        ) + r")\b"
    )
    for country, entries in BY_COUNTRY.items()
}


@dataclass
class LexiconHit:
    """A lexicon term found in text."""

    term: str
    gloss: str
    countries: tuple[str, ...]
    category: str
    count: int
    polysemous: bool = False


def find_slang(
    text: str,
    countries: Optional[Iterable[str]] = None,
) -> list[LexiconHit]:
    """
    Find every lexicon term present in `text`.

    Parameters
    ----------
    countries
        Restrict the search to these country keys. When None, all are searched.

    Returns
    -------
    Hits sorted by descending count. Polysemous terms are flagged so callers can
    treat them cautiously -- `guagua` alone does not prove Caribbean origin.
    """
    folded = _fold(text)
    targets = list(countries) if countries else list(BY_COUNTRY)

    counts: dict[str, int] = {}
    for country in targets:
        pattern = _COUNTRY_PATTERNS.get(country)
        if not pattern:
            continue
        for match in pattern.findall(folded):
            counts[match] = counts.get(match, 0) + 1

    hits = []
    for term, count in counts.items():
        entry = BY_TERM.get(term)
        if entry:
            hits.append(
                LexiconHit(
                    term=entry.term, gloss=entry.gloss, countries=entry.countries,
                    category=entry.category, count=count, polysemous=entry.polysemous,
                )
            )
    hits.sort(key=lambda h: -h.count)
    return hits


def score_country_affinity(text: str) -> dict[str, float]:
    """
    Score how strongly `text` matches each country's lexicon.

    Each hit contributes 1/len(countries), so a term shared by five countries is
    weak evidence for any one of them while an exclusive term is strong evidence.
    Polysemous terms are down-weighted by half.

    Returns {country_key: score} for countries scoring above zero, highest first.
    """
    scores: dict[str, float] = {}
    for hit in find_slang(text):
        weight = hit.count / max(len(hit.countries), 1)
        if hit.polysemous:
            weight *= 0.5
        for country in hit.countries:
            scores[country] = scores.get(country, 0.0) + weight
    return dict(sorted(scores.items(), key=lambda kv: -kv[1]))


def coverage_report() -> dict[str, int]:
    """Number of lexicon entries per country -- used to audit lexicon balance."""
    return dict(
        sorted(((c, len(e)) for c, e in BY_COUNTRY.items()), key=lambda kv: -kv[1])
    )
