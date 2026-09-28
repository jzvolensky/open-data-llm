from __future__ import annotations

from collections.abc import Sequence

from .base import Message

SYSTEM = (
    "Si asistent pre otvorené dáta mesta Bratislava (data.bratislava.sk). "
    "Odpovedaj v jazyku otázky (slovensky alebo anglicky). "
    "Vychádzaj výhradne z poskytnutého kontextu a výsledkov dopytu. "
    "Odpovedz stručne: 2-4 vety, zoznam len ak uvádzaš datasety (max 3). "
    "Neopisuj celé metadáta. Uveď názvy použitých datasetov a ich URL. "
    "Ak je uvedený vypočítaný výsledok dopytu, prezentuj ho ako vypočítaný z daného "
    "datasetu a uveď, podľa čoho bol filtrovaný. "
    "Ak odpoveď v kontexte ani výsledku nie je, jasne povedz, že to nevieš."
)

SQL_SYSTEM = (
    "Si expert na DuckDB SQL. Na základe schémy tabuľky vygeneruj jeden SELECT dotaz, "
    "ktorý odpovie na otázku. Použi iba uvedenú tabuľku a uvedené stĺpce "
    "(presne tak, ako sú napísané). Názvy stĺpcov s medzerou alebo diakritikou obaľ "
    'do dvojitých úvodzoviek, napr. "Katastrálne územie"; reťazcové hodnoty do '
    "jednoduchých úvodzoviek. Pridaj iba filtre, na ktoré sa otázka pýta; "
    "nedopĺňaj ďalšie obmedzenia. Rešpektuj nápovedu o filtrovaní a zoznam prípustných "
    "hodnôt, ak sú uvedené. Ak tabuľka neobsahuje stĺpce potrebné na odpoveď, vráť "
    "presne NO_DATA. Vráť iba SQL alebo NO_DATA, bez vysvetlenia."
)

def build_messages(
    query: str,
    context: str,
    data_block: str | None = None,
) -> list[Message]:
    parts = [f"Kontext:\n{context}"]
    if data_block:
        parts.append(f"Výsledok dopytu:\n{data_block}")
    parts.append(f"Otázka: {query}")
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": "\n\n".join(parts)},
    ]


def build_sql_messages(
    query: str,
    table: str,
    schema: str,
    title: str | None = None,
    hints: Sequence[str] | None = None,
    values: Sequence[str] | None = None,
) -> list[Message]:
    header = f"Dataset: {title}\n" if title else ""
    hint_text = ("\nNápoveda: " + " ".join(hints)) if hints else ""
    value_text = ("\n" + "\n".join(values)) if values else ""
    return [
        {"role": "system", "content": SQL_SYSTEM},
        {
            "role": "user",
            "content": (
                f"{header}Tabuľka: {table}\nStĺpce: {schema}{hint_text}{value_text}\n"
                f"Otázka: {query}\nVráť iba SELECT alebo NO_DATA."
            ),
        },
    ]


REWRITE_SYSTEM = (
    "Prepíš poslednú otázku používateľa na samostatnú otázku, ktorá dáva zmysel bez "
    "predchádzajúceho kontextu. Zachovaj jazyk aj význam a doplň chýbajúce údaje "
    "(napr. mestskú časť alebo rok) z konverzácie. Vráť iba prepísanú otázku, "
    "bez vysvetlenia."
)


def build_rewrite_messages(
    query: str, history: Sequence[dict[str, str]], max_turns: int = 6
) -> list[Message]:
    recent = history[-max_turns:]
    conversation = "\n".join(
        f"{turn.get('role', 'user')}: {turn.get('content', '')}".strip()
        for turn in recent
    )
    return [
        {"role": "system", "content": REWRITE_SYSTEM},
        {
            "role": "user",
            "content": (
                f"Konverzácia:\n{conversation}\n\n"
                f"Posledná otázka: {query}\nSamostatná otázka:"
            ),
        },
    ]


def build_context(sources: Sequence[dict[str, str]], max_chars: int = 350) -> str:
    blocks: list[str] = []
    for index, source in enumerate(sources, start=1):
        card = (source.get("card") or "").strip()
        snippet = card[:max_chars]
        blocks.append(
            f"[{index}] {source.get('title', '')}\n"
            f"URL: {source.get('url', '')}\n"
            f"{snippet}"
        )
    return "\n\n".join(blocks) if blocks else "(žiadne datasety)"
