"""Запускает SQL-блоки из markdown-файлов и печатает результаты.

Из корня репозитория:

    python3 src/run_sql.py analysis/01_activity_and_stickiness.md
        все блоки ```sql из файла по порядку, с результатами

    python3 src/run_sql.py analysis/01_activity_and_stickiness.md "Липкость"
        только блоки под заголовком, где есть этот текст

    python3 src/run_sql.py -e "SELECT COUNT(*) FROM newcomers"
        один свой запрос, без файла

    python3 src/run_sql.py analysis/03_hypotheses.md analysis/04_prioritization.md
        несколько файлов: все, кроме последнего, выполняются молча
        (например, чтобы создать VIEW), результаты печатаются только для последнего

Как это работает:
  - база собирается через db.connect() из файлов в data/ и analysis/rice.csv;
  - блоки ```sql выполняются сверху вниз в одной базе: представление или таблица,
    созданные в раннем блоке или файле, доступны во всех следующих;
  - рядом с результатом печатается заголовок раздела и строка «**Итог:**» из файла,
    чтобы сразу сверить число с текстом.
"""

import sqlite3
import sys

from db import connect

MAX_ROWS = 100


def is_blank(sql):
    """True, если в тексте нет ничего, кроме пустых строк и комментариев --."""
    return all(not ln.strip() or ln.strip().startswith("--") for ln in sql.splitlines())


def split_statements(sql):
    """Делит текст блока на отдельные запросы по ';' (точка с запятой внутри кавычек не режет)."""
    statements, buf = [], ""
    for ch in sql:
        buf += ch
        if ch == ";" and sqlite3.complete_statement(buf):
            if not is_blank(buf):
                statements.append(buf.strip())
            buf = ""
    if not is_blank(buf):
        statements.append(buf.strip())
    return statements


def run_statement(con, stmt):
    try:
        cur = con.execute(stmt)
    except sqlite3.Error as e:
        print(f"    ОШИБКА: {e}")
        return
    if cur.description is None:
        print("    ok")
        return
    rows = cur.fetchall()
    for row in rows[:MAX_ROWS]:
        print("   ", row)
    if len(rows) > MAX_ROWS:
        print(f"    … ещё {len(rows) - MAX_ROWS} строк")
    if not rows:
        print("    (пусто)")


def blocks_from_markdown(path):
    """Список (заголовок, строка итога, текст sql) по порядку."""
    heading, answer = "", ""
    in_sql, buf, result = False, [], []
    with open(path, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if in_sql:
                if stripped.startswith("```"):
                    result.append((heading, answer, "".join(buf)))
                    in_sql, buf = False, []
                else:
                    buf.append(line)
            elif stripped.lower().startswith("```sql"):
                in_sql = True
            elif stripped.startswith("#"):
                heading, answer = stripped.lstrip("#").strip(), ""
            elif stripped.startswith("**Итог:**"):
                answer = stripped
    if in_sql:
        print(f"[!] {heading}: блок ```sql не закрыт — выполняю его до конца файла\n")
        result.append((heading, answer, "".join(buf)))
    return result


def run_quietly(con, path):
    """Выполняет блоки файла без вывода результатов — только ошибки."""
    for heading, _, sql in blocks_from_markdown(path):
        for stmt in split_statements(sql):
            try:
                con.execute(stmt).fetchall()
            except sqlite3.Error as e:
                print(f"[!] {heading}: {e}")


def run_verbose(con, blocks, only):
    """Выполняет блоки и печатает результаты (только под подходящими заголовками, если задан фильтр)."""
    last_heading = None
    for heading, answer, sql in blocks:
        if is_blank(sql):
            if only and only in heading.lower():
                print(f"{heading}: блок ```sql пустой")
            continue
        if only and only not in heading.lower():
            # блок не показываем, но выполняем: он может создавать VIEW для следующих
            for stmt in split_statements(sql):
                try:
                    con.execute(stmt).fetchall()
                except sqlite3.Error as e:
                    print(f"[!] {heading}: {e}")
            continue
        if heading != last_heading:
            print("=" * 70)
            print(heading)
            if answer:
                print(answer)
            last_heading = heading
        for stmt in split_statements(sql):
            print("-" * 70)
            print("   ", stmt.replace("\n", "\n    "))
            print("  →")
            run_statement(con, stmt)


def main(argv):
    args = argv[1:]
    query = None
    if "-e" in args:
        i = args.index("-e")
        if i + 1 >= len(args):
            print(__doc__)
            return 1
        query = args[i + 1]
        args = args[:i] + args[i + 2:]
    files = [a for a in args if a.lower().endswith(".md")]
    rest = [a for a in args if not a.lower().endswith(".md")]
    if len(rest) > 1 or (query is None and not files):
        print(__doc__)
        return 1
    only = rest[0].lower() if rest else None

    con = connect()

    if query is not None:
        for path in files:
            run_quietly(con, path)
        for stmt in split_statements(query):
            run_statement(con, stmt)
        return 0

    for path in files[:-1]:
        run_quietly(con, path)
    blocks = blocks_from_markdown(files[-1])
    if not blocks:
        print("В файле нет блоков ```sql")
        return 1
    if all(is_blank(sql) for _, _, sql in blocks):
        print("Все блоки ```sql пока пустые — впиши запросы.")
        return 0
    if only and not any(only in h.lower() for h, _, _ in blocks):
        print(f"Нет заголовка, в котором есть «{rest[0]}»")
        return 1
    run_verbose(con, blocks, only)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
