#!/usr/bin/env python3
"""Render the proof chart from campaign.json.

    .venv/bin/python plot_campaign.py            # re-render without re-running

`simulate_campaign.py` calls this at the end of a run. It is kept separate so
the chart can be redrawn from the committed numbers in a second, without
spending the thirty-five seconds of the campaign, and so the only thing this
file ever reads is `campaign.json`.

matplotlib lives here and in the evaluator, never in `core/`. The web app
draws its own charts in the browser from this same JSON, because the visitor's
rounds extend the curve live and a rendered image cannot.

Two panels, because the naive-pooling arm makes two different claims and
conflating them would overstate the weaker one:

  left   what the lab would report -- cumulative best observed affinity
  right  what you would act on -- the true value of the design each arm's own
         project state ranks first
"""

import json
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.abspath(__file__))
DEFAULT_IN = os.path.join(REPO, "web", "public", "assets", "campaign.json")

# Validated categorical slots 1-3, light and dark. Colour follows the arm, not
# its rank, so an arm keeps its hue in every panel and every mode.
THEME = {
    "light": {
        "surface": "#fcfcfb", "ink": "#0b0b0b", "ink2": "#52514e", "muted": "#898781",
        "grid": "#e1e0d9", "axis": "#c3c2b7",
        "series": {"guided": "#2a78d6", "random": "#eb6834", "guided_naive": "#1baf7a"},
    },
    "dark": {
        "surface": "#1a1a19", "ink": "#ffffff", "ink2": "#c3c2b7", "muted": "#898781",
        "grid": "#2c2c2a", "axis": "#383835",
        "series": {"guided": "#3987e5", "random": "#d95926", "guided_naive": "#199e70"},
    },
}
LABEL = {
    "guided": "Model-guided",
    "random": "Random",
    "guided_naive": "Guided, pooled naively",
}
ORDER = ("guided", "random", "guided_naive")


def _panel(ax, payload, arms, key, theme, title, subtitle):
    t = THEME[theme]
    rounds = np.arange(1, payload["n_rounds"] + 1)
    threshold = payload["threshold_pkd"]

    ax.set_facecolor(t["surface"])
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(t["axis"])
        ax.spines[spine].set_linewidth(1.0)
    ax.grid(True, axis="y", color=t["grid"], linewidth=1.0, zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(colors=t["muted"], labelsize=9, length=0)

    # The threshold is a real threshold, so it is the one dashed rule here.
    # Labelled below the rule at the right edge: every arm has left that space
    # by round 3, so the label lands on the surface rather than on a band.
    ax.axhline(threshold, color=t["muted"], linewidth=1.2, linestyle=(0, (5, 4)), zorder=1)
    ax.annotate("amended threshold  %.3f" % threshold,
                xy=(payload["n_rounds"] + 0.78, threshold), xytext=(0, -7),
                textcoords="offset points", ha="right", va="top",
                fontsize=8.5, color=t["muted"])

    # Where the assay version changes. Both panels, because it bites in both.
    ax.axvspan(3.5, payload["n_rounds"] + 0.85, color=t["muted"], alpha=0.05,
               linewidth=0, zorder=0)

    ends = []
    for arm in arms:
        q = [r[key] for r in payload["summary"][arm]["per_round"]]
        med = np.array([x["median"] for x in q])
        lo = np.array([x["q1"] for x in q])
        hi = np.array([x["q3"] for x in q])
        c = t["series"][arm]
        ax.fill_between(rounds, lo, hi, color=c, alpha=0.14, linewidth=0, zorder=2)
        ax.plot(rounds, med, color=c, linewidth=2.0, zorder=4,
                solid_capstyle="round", label=LABEL[arm])
        ax.plot(rounds, med, "o", color=c, markersize=4.5, zorder=5,
                markeredgecolor=t["surface"], markeredgewidth=2.0)
        ends.append((float(med[-1]), c))

    # Direct labels at the endpoint. Slot 3 sits below 3:1 on the light
    # surface, so the label is the relief, not a nicety.
    #
    # Two arms can finish within a few hundredths of each other -- at the
    # amended threshold the naive arm lands on random's line in the right
    # panel -- so the labels are pushed apart before they are drawn. The
    # marker stays on the true value; only the text moves. The gap is a
    # fraction of the autoscaled range rather than a pixel count, so it
    # survives tight_layout and both output dpi settings.
    # The threshold rule is an occupant of the same strip and is seeded into
    # the list as a blocker with no label of its own: an arm that finishes on
    # the gate would otherwise have the dashes drawn through its digits.
    span = ax.get_ylim()[1] - ax.get_ylim()[0]
    gap, placed = 0.045 * span, []
    for value, c in sorted(ends + [(threshold, None)], key=lambda e: e[0]):
        y = value if not placed or value - placed[-1] >= gap else placed[-1] + gap
        placed.append(y)
        if c is None:
            continue
        ax.annotate("%.2f" % value, xy=(rounds[-1], y), xytext=(7, -3),
                    textcoords="offset points", ha="left", va="center",
                    fontsize=9.5, color=c, fontweight="bold")

    ax.set_xticks(rounds)
    ax.set_xticklabels(["R%d" % r for r in rounds])
    ax.set_xlim(rounds[0] - 0.15, rounds[-1] + 0.85)
    ax.set_xlabel("experimental round", fontsize=9, color=t["ink2"], labelpad=8)
    ax.set_title(title, fontsize=12, color=t["ink"], fontweight="bold",
                 loc="left", pad=26)
    ax.annotate(subtitle, xy=(0, 1.0), xycoords="axes fraction", xytext=(0, 7),
                textcoords="offset points", ha="left", va="bottom",
                fontsize=9, color=t["ink2"])
    return ax


def render(payload, out_path, theme="light"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    t = THEME[theme]
    arms = [a for a in ORDER if a in payload["summary"]]
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
        "svg.fonttype": "none",
    })

    # One shared y-axis across both panels: same unit, and the whole point is
    # that an arm reports 11.05 while acting on 11.23. Different scales would
    # hide exactly the comparison the right-hand panel exists to make.
    fig, axes = plt.subplots(1, 2, figsize=(12.6, 5.6), facecolor=t["surface"], sharey=True)
    _panel(axes[0], payload, arms, "best_observed", theme,
           "What the lab would report",
           "cumulative best observed affinity, median with interquartile band")
    _panel(axes[1], payload, arms, "nominated_true", theme,
           "What you would act on",
           "true affinity of the design each arm's own state ranks first")
    axes[0].set_ylabel("pKD  (higher is better)", fontsize=9, color=t["ink2"], labelpad=8)

    for ax in axes:
        ax.annotate("assay v1.3", xy=(3.6, 0.02), xycoords=("data", "axes fraction"),
                    ha="left", va="bottom", fontsize=8.5, color=t["muted"])

    handles, labels = axes[0].get_legend_handles_labels()
    leg = fig.legend(handles, labels, loc="upper left", bbox_to_anchor=(0.058, 0.930),
                     ncol=3, frameon=False, fontsize=9.5, handlelength=1.6,
                     columnspacing=1.8, handletextpad=0.6)
    for text in leg.get_texts():
        text.set_color(t["ink2"])

    fig.suptitle("Model-guided selection against random, %d seeds per arm"
                 % payload["n_seeds"],
                 x=0.058, y=0.972, ha="left", fontsize=15,
                 color=t["ink"], fontweight="bold")
    fig.text(0.058, 0.032,
             "SYNTHETIC LANDSCAPE.  This shows the decision loop converges. It does not "
             "show that the method finds better antibodies.",
             ha="left", fontsize=8.5, color=t["muted"])
    fig.text(0.942, 0.032, "landscape %s" % payload["landscape_build_hash"][7:19],
             ha="right", fontsize=8.5, color=t["muted"], family="monospace")

    fig.tight_layout(rect=(0.045, 0.065, 0.955, 0.895))
    fig.savefig(out_path, facecolor=t["surface"], dpi=200 if out_path.endswith(".png") else None)
    plt.close(fig)
    return out_path


def render_all(payload, base=None):
    base = base or os.path.join(REPO, "web", "public", "assets", "campaign")
    os.makedirs(os.path.dirname(base), exist_ok=True)
    written = []
    for theme in ("light", "dark"):
        suffix = "" if theme == "light" else "-dark"
        for ext in ("png", "svg"):
            written.append(render(payload, "%s%s.%s" % (base, suffix, ext), theme))
    return written


def main(argv=None):
    src = (argv or sys.argv[1:] or [DEFAULT_IN])[0]
    payload = json.load(open(src))
    for path in render_all(payload):
        print("wrote %s" % os.path.relpath(path, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
