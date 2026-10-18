"""Сборка базы SQLite в памяти для всех запросов проекта.

После connect() в базе есть таблицы:

  users      все пользователи: user_id, signup_date (дата регистрации)

  activity   активность по дням: user_id, date, games, wins, puzzles, lessons.
             Одна строка = один пользователь в один день, когда он заходил на сайт.
             games, wins: партии и победы, puzzles: решённые задачи, lessons: пройденные уроки.
             Если пользователя в какой-то день нет в activity, в этот день он не заходил.

  act        то же, что activity, плюс готовые поля:
             signup_date, signup_month (ГГГГ-ММ) регистрации пользователя,
             day_n  день с регистрации (0: день регистрации, 1: следующий и так далее),
             week   понедельник недели, к которой относится день,
             month  месяц этого дня (ГГГГ-ММ)

  newcomers  новички (зарегистрировались с 1 июля 2026), по строке на человека:
             user_id, signup_date, signup_month,
             games0, wins0, puzzles0, lessons0  что делал в день регистрации,
             back_d1   1, если заходил на следующий день,
             back_d7   1, если заходил ровно на 7-й день,
             back_w1   1, если заходил хотя бы раз в дни с 1-го по 7-й,
             days_30   в сколько дней из дней с 1-го по 30-й заходил,
             full_week, full_month  1, если вся неделя или весь месяц после
                       регистрации уже есть в выгрузке. У новичков последних дней
                       back_w1 и days_30 неполные, их отсекают условием full_week = 1
                       или full_month = 1.

  cohorts    когортный отчёт из data/cohort_report.csv:
             cohort (дата регистрации), d0 ... d30: сколько человек из когорты
             заходили на сайт в день 0 ... 30. Пустая ячейка = этот день ещё
             не наступил, в базе NULL.

  rice       оценки гипотез из analysis/rice.csv:
             id, name, reach, impact, confidence, effort, principles, comment.
             Дробные числа в CSV пишутся через точку: 0.5.

Использование в своём скрипте (из корня репозитория):

    from db import connect
    con = connect()
    print(con.execute("SELECT COUNT(*) FROM users").fetchone())
"""

import csv
import sqlite3
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
DATA_DIR = SRC_DIR.parent / "data"

PREPARE = """
CREATE INDEX activity_user ON activity(user_id, date);

CREATE TABLE act AS
SELECT a.*, u.signup_date, substr(u.signup_date, 1, 7) AS signup_month,
       CAST(julianday(a.date) - julianday(u.signup_date) AS INTEGER) AS day_n,
       date(a.date, '-6 days', 'weekday 1') AS week,
       substr(a.date, 1, 7) AS month
FROM activity a JOIN users u ON u.user_id = a.user_id
ORDER BY a.date, a.user_id;

CREATE TABLE newcomers AS
SELECT u.user_id, u.signup_date, substr(u.signup_date, 1, 7) AS signup_month,
       a.games AS games0, a.wins AS wins0, a.puzzles AS puzzles0, a.lessons AS lessons0,
       EXISTS (SELECT 1 FROM activity b WHERE b.user_id = u.user_id
               AND b.date = date(u.signup_date, '+1 day')) AS back_d1,
       EXISTS (SELECT 1 FROM activity b WHERE b.user_id = u.user_id
               AND b.date = date(u.signup_date, '+7 days')) AS back_d7,
       EXISTS (SELECT 1 FROM activity b WHERE b.user_id = u.user_id
               AND b.date BETWEEN date(u.signup_date, '+1 day')
                              AND date(u.signup_date, '+7 days')) AS back_w1,
       (SELECT COUNT(*) FROM activity b WHERE b.user_id = u.user_id
               AND b.date BETWEEN date(u.signup_date, '+1 day')
                              AND date(u.signup_date, '+30 days')) AS days_30,
       date(u.signup_date, '+7 days') <= (SELECT MAX(date) FROM activity) AS full_week,
       date(u.signup_date, '+30 days') <= (SELECT MAX(date) FROM activity) AS full_month
FROM users u
JOIN activity a ON a.user_id = u.user_id AND a.date = u.signup_date
WHERE u.signup_date >= (SELECT MIN(date) FROM activity)
ORDER BY u.user_id;
"""

RICE_COLUMNS = ["id", "name", "reach", "impact", "confidence", "effort", "principles", "comment"]
RICE_NUMBERS = {"reach", "impact", "confidence", "effort"}


def _read_csv(path):
    """Читает CSV: разделитель — запятая или точка с запятой (так иногда сохраняет Calc)."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        text = f.read()
    first = text.splitlines()[0] if text else ""
    delimiter = ";" if first.count(";") > first.count(",") else ","
    rows = list(csv.reader(text.splitlines(), delimiter=delimiter))
    return [row for row in rows if any(cell.strip() for cell in row)]


def _load_table(con, table, path, columns):
    """Грузит CSV в таблицу. columns — список (имя, тип); пустая ячейка превращается в NULL."""
    con.execute(f"CREATE TABLE {table} ({', '.join(f'{n} {t}' for n, t in columns)})")
    rows = []
    for row in _read_csv(path)[1:]:
        values = []
        for (name, kind), value in zip(columns, row):
            if value == "":
                values.append(None)
            elif kind.startswith("INTEGER"):
                values.append(int(value))
            else:
                values.append(value)
        rows.append(values)
    con.executemany(f"INSERT INTO {table} VALUES ({', '.join('?' for _ in columns)})", rows)


def _load_rice(con):
    """Грузит analysis/rice.csv: числовые колонки становятся числами, текст остаётся как есть."""
    con.execute(f"CREATE TABLE rice ({', '.join(RICE_COLUMNS)})")
    path = SRC_DIR.parent / "analysis" / "rice.csv"
    if not path.exists():
        return
    rows = _read_csv(path)
    if not rows:
        return
    header = [h.strip().lower() for h in rows[0]]
    if header[:len(RICE_COLUMNS)] != RICE_COLUMNS:
        print(f"[!] rice.csv: первая строка должна быть «{','.join(RICE_COLUMNS)}» — таблица rice пустая\n")
        return
    for line_no, row in enumerate(rows[1:], start=2):
        if len(row) > len(RICE_COLUMNS):
            print(f"[!] rice.csv, строка {line_no}: колонок больше, чем в первой строке — строка пропущена. "
                  f"Скорее всего, дробное число записано через запятую: пиши 0.5, "
                  f"а текст с запятой бери в двойные кавычки")
            continue
        row = (row + [""] * len(RICE_COLUMNS))[:len(RICE_COLUMNS)]
        values = []
        for name, value in zip(RICE_COLUMNS, row):
            value = value.strip()
            if value == "":
                values.append(None)
            elif name in RICE_NUMBERS:
                try:
                    values.append(float(value.replace(",", ".").replace("%", "").replace(" ", "").replace("\u00a0", "")))
                except ValueError:
                    print(f"[!] rice.csv, строка {line_no}: в колонке {name} не число: «{value}»")
                    values.append(None)
            else:
                values.append(value)
        con.execute(f"INSERT INTO rice VALUES ({', '.join('?' for _ in RICE_COLUMNS)})", values)


def connect(path=":memory:"):
    """Возвращает соединение с базой, где уже лежат все таблицы из описания выше."""
    con = sqlite3.connect(path)
    _load_table(con, "users", DATA_DIR / "users.csv",
                [("user_id", "INTEGER PRIMARY KEY"), ("signup_date", "TEXT")])
    _load_table(con, "activity", DATA_DIR / "activity.csv",
                [("user_id", "INTEGER"), ("date", "TEXT"), ("games", "INTEGER"),
                 ("wins", "INTEGER"), ("puzzles", "INTEGER"), ("lessons", "INTEGER")])
    _load_table(con, "cohorts", DATA_DIR / "cohort_report.csv",
                [("cohort", "TEXT")] + [(f"d{k}", "INTEGER") for k in range(31)])
    con.executescript(PREPARE)
    _load_rice(con)
    con.commit()
    return con


if __name__ == "__main__":
    con = connect()
    for table in ("users", "activity", "act", "newcomers", "cohorts", "rice"):
        n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"{table}: {n} строк")
