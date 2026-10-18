"""График по одному SQL-запросу: чтобы увидеть числа глазами.

Из корня репозитория:

    python3 src/chart.py "SELECT date, COUNT(DISTINCT user_id) AS dau FROM act GROUP BY date" dau

Результат: файл src/charts/dau.html, его нужно открыть в браузере.

Как устроен запрос:
  - первая колонка: подписи по горизонтали (дата, неделя, номер дня);
  - каждая следующая колонка: отдельная линия, имя линии = имя колонки (AS dau);
  - строки рисуются в том порядке, в каком их вернул запрос, нужен порядок: добавь ORDER BY.
Наведи мышь на точку: появятся подпись и значение.
"""

import html
import sys
from pathlib import Path

from db import connect

COLORS = ["#1f6feb", "#d1242f", "#1a7f37", "#9a6700", "#8250df", "#57606a"]
W, H = 960, 380
LEFT, RIGHT, TOP, BOTTOM = 60, 20, 20, 70


def build_svg(labels, series):
    top_value = max((v for _, values in series for v in values if v is not None), default=0) or 1
    n = len(labels)
    step_x = (W - LEFT - RIGHT) / max(n - 1, 1)

    def x(i):
        return LEFT + i * step_x

    def y(v):
        return TOP + (H - TOP - BOTTOM) * (1 - v / top_value)

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%">']
    for k in range(5):
        v = top_value * k / 4
        parts.append(f'<line x1="{LEFT}" x2="{W - RIGHT}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grid"/>')
        label = f"{v:.0f}" if top_value >= 10 else f"{v:.2g}"
        parts.append(f'<text x="{LEFT - 6}" y="{y(v) + 4:.1f}" text-anchor="end">{label}</text>')
    every = max(1, n // 15)
    for i, label in enumerate(labels):
        if i % every == 0 or i == n - 1:
            parts.append(f'<text x="{x(i):.1f}" y="{H - BOTTOM + 14}" text-anchor="end" '
                         f'transform="rotate(-45 {x(i):.1f} {H - BOTTOM + 14})">{html.escape(str(label))}</text>')
    for (name, values), color in zip(series, COLORS):
        points = [(x(i), y(v)) for i, v in enumerate(values) if v is not None]
        path = " ".join(f"{px:.1f},{py:.1f}" for px, py in points)
        parts.append(f'<polyline points="{path}" fill="none" stroke="{color}" stroke-width="2"/>')
        for i, v in enumerate(values):
            if v is not None:
                parts.append(f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="3" fill="{color}">'
                             f'<title>{html.escape(str(labels[i]))}: {name} = {v:g}</title></circle>')
    parts.append("</svg>")
    return "\n".join(parts)


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 1
    query, name = argv[1], argv[2]
    con = connect()
    cur = con.execute(query)
    columns = [d[0] for d in cur.description]
    rows = cur.fetchall()
    if len(columns) < 2 or not rows:
        print("Нужен запрос хотя бы с двумя колонками и хотя бы одной строкой.")
        return 1
    labels = [r[0] for r in rows]
    series = []
    for j, col in enumerate(columns[1:], start=1):
        values = []
        for r in rows:
            v = r[j]
            values.append(float(v) if isinstance(v, (int, float)) else None)
        series.append((col, values))
    legend = " ".join(f'<span style="color:{c}">■ {html.escape(n)}</span>' for (n, _), c in zip(series, COLORS))
    page = f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>{html.escape(name)}</title>
<style>
body {{ font-family: sans-serif; margin: 24px; color: #1f2328; }}
svg text {{ font-size: 11px; fill: #57606a; }}
.grid {{ stroke: #d0d7de; stroke-width: 1; }}
code {{ background: #f6f8fa; padding: 2px 4px; }}
</style></head><body>
<h2>{html.escape(name)}</h2>
<p><code>{html.escape(query)}</code></p>
<p>{legend}</p>
{build_svg(labels, series)}
</body></html>
"""
    out = Path(__file__).resolve().parent / "charts" / f"{name}.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(f"Готово: src/charts/{name}.html — открой в браузере")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
