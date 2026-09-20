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
    "(presne tak, ako sú napísané). Rešpektuj nápovedu o filtrovaní, ak je uvedená. "
    "Ak tabuľka neobsahuje stĺpce potrebné na odpoveď, vráť presne NO_DATA. "
    "Vráť iba SQL alebo NO_DATA, bez vysvetlenia."
)

VERIFY_SYSTEM = (
    "Si prísny kontrolór. Dostaneš otázku, schému tabuľky, SQL a výsledok. "
    "Odpovedz iba YES alebo NO. "
    "YES len ak SQL naozaj odpovedá na otázku pomocou uvedenej tabuľky a stĺpcov "
    "(napr. správne filtruje hľadané územie a počíta to, na čo sa otázka pýta). "
    "Inak NO."
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
) -> list[Message]:
    header = f"Dataset: {title}\n" if title else ""
    hint_text = ("\nNápoveda: " + " ".join(hints)) if hints else ""
    return [
        {"role": "system", "content": SQL_SYSTEM},
        {
            "role": "user",
            "content": (
                f"{header}Tabuľka: {table}\nStĺpce: {schema}{hint_text}\n"
                f"Otázka: {query}\nVráť iba SELECT alebo NO_DATA."
            ),
        },
    ]


def build_verify_messages(
    query: str,
    table: str,
    schema: str,
    sql: str,
    result: str,
) -> list[Message]:
    return [
        {"role": "system", "content": VERIFY_SYSTEM},
        {
            "role": "user",
            "content": (
                f"Otázka: {query}\nTabuľka: {table}\nStĺpce: {schema}\n"
                f"SQL: {sql}\nVýsledok:\n{result}\n"
                "Odpovedá to na otázku? Odpovedz iba YES alebo NO."
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
