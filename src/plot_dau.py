"""График DAU по дням с двумя наплывами регистраций и провалом 19 августа.

Из корня репозитория: python3 src/plot_dau.py  (нужен matplotlib)
Результат: analysis/dau.png
"""

from datetime import date
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt

from db import connect

OUT = Path(__file__).resolve().parent.parent / "analysis" / "dau.png"

con = connect()
rows = con.execute(
    "SELECT date, COUNT(DISTINCT user_id) FROM act GROUP BY date ORDER BY date"
).fetchall()
days = [date.fromisoformat(d) for d, _ in rows]
dau = [v for _, v in rows]

fig, ax = plt.subplots(figsize=(9, 4))
ax.plot(days, dau, color="#1f6feb", linewidth=1.6)
ax.axvspan(date(2026, 8, 7), date(2026, 8, 13), color="#f0b429", alpha=0.3)
ax.axvspan(date(2026, 8, 28), date(2026, 8, 31), color="#f0b429", alpha=0.3)
ax.annotate("наплыв регистраций\n7–13 августа", (date(2026, 8, 10), 3950),
            ha="center", va="bottom", fontsize=9)
ax.annotate("второй наплыв\n28–31 августа", (date(2026, 8, 29), 3300),
            ha="left", va="bottom", fontsize=9, xytext=(6, 0), textcoords="offset points")
ax.annotate("19 августа: провал\n935 заходов", (date(2026, 8, 19), 935),
            xytext=(date(2026, 8, 22), 300), fontsize=9,
            arrowprops=dict(arrowstyle="->", color="#555"))
ax.set_title("Заходы на сайт по дням (DAU), 1 июля – 28 сентября 2026")
ax.set_ylabel("уникальных пользователей в день")
ax.set_ylim(0, 4600)
ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0, interval=2))
ax.grid(axis="y", alpha=0.3)
fig.tight_layout()
fig.savefig(OUT, dpi=150)
print(f"Сохранено: {OUT}")
