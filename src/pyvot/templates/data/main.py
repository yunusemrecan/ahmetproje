"""{{name}}: {{t:data_doc}}"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # {{t:data_agg_comment}}
import matplotlib.pyplot as plt
import pandas as pd

HERE = Path(__file__).parent


def main() -> None:
    df = pd.read_csv(HERE / "data" / "sample.csv")
    print(df.head())
    print()
    print(df.describe())

    totals = df.groupby("{{t:col_city}}")["{{t:col_sales}}"].sum().sort_values(ascending=False)
    print()
    print(totals)

    ax = totals.plot(
        kind="bar",
        title="{{t:chart_title}}",
        ylabel="{{t:col_sales}}",
        rot=0,
    )
    ax.figure.tight_layout()
    out = HERE / "chart.png"
    ax.figure.savefig(out, dpi=120)
    plt.close(ax.figure)
    print()
    print("{{t:chart_saved}}", out)


if __name__ == "__main__":
    main()
