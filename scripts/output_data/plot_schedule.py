"""
Generate a Gantt chart from a solution JSON produced by milp_pyomo.get_solution().

Usage:
    python plot_schedule.py solution.json
    python plot_schedule.py solution.json --output schedule.png
"""
import argparse
import json

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches


def plot_schedule(solution: dict, output_path: str | None = None) -> None:
    aircraft_list = solution["aircraft"]
    positions = sorted({a["position"] for a in aircraft_list})
    colors = plt.cm.tab10.colors

    # One row per position, colour per aircraft
    aircraft_ids = [a["id"] for a in aircraft_list]
    color_map = {r: colors[i % len(colors)] for i, r in enumerate(aircraft_ids)}
    pos_index = {p: i for i, p in enumerate(positions)}

    fig, ax = plt.subplots(figsize=(12, max(3, len(positions) * 1.5)))

    patch_data: dict = {}  # Rectangle patch -> job metadata for hover tooltips

    for aircraft in aircraft_list:
        r = aircraft["id"]
        p = aircraft["position"]
        y = pos_index[p]
        color = color_map[r]

        for job in aircraft["jobs"]:
            start  = job["start"]
            finish = job["finish"]
            duration = finish - start
            container = ax.barh(y, duration, left=start, height=0.5, color=color,
                                edgecolor="white", linewidth=0.8)
            patch_data[container[0]] = {
                "job_id":   job["id"],
                "aircraft": r,
                "start":    start,
                "finish":   finish,
            }
            ax.text(start + duration / 2, y, job["id"],
                    ha="center", va="center", fontsize=8, color="white", fontweight="bold")

    # Axes formatting
    ax.set_yticks(range(len(positions)))
    ax.set_yticklabels(positions)
    ax.set_xlabel("Time")
    ax.set_ylabel("Position")

    metrics = solution["metrics"]
    instance = solution.get("instance", "")
    label    = solution.get("label") or solution.get("solver", "")
    obj      = solution.get("objective", "")

    # Config params: skip implementation-detail keys, format compactly
    _SKIP = {"log_enabled"}
    config = solution.get("config", {})
    config_str = "  ".join(
        f"{k}={v}" for k, v in config.items() if k not in _SKIP
    )

    line1_parts = [p for p in [instance, label] if p]
    line1_parts += [f"obj={obj}"] if obj != "" else []
    line1 = "   |   ".join(line1_parts)

    line2 = (
        f"makespan={metrics['makespan']}  "
        f"movements={metrics['movements']}  "
        f"delay={metrics['total_delay']}"
    )
    if config_str:
        line2 += f"   |   {config_str}"

    ax.set_title(f"{line1}\n{line2}", fontsize=9)

    # Legend
    legend_handles = [
        mpatches.Patch(color=color_map[r], label=r) for r in aircraft_ids
    ]
    ax.legend(handles=legend_handles, loc="upper right")
    ax.invert_yaxis()

    # Hover tooltips: show job id, start and finish on mouse-over
    try:
        import mplcursors
        cursor = mplcursors.cursor(list(patch_data.keys()), hover=True)

        @cursor.connect("add")
        def on_add(sel):
            data = patch_data[sel.artist]
            sel.annotation.set_text(
                f"{data['job_id']}  ({data['aircraft']})\n"
                f"Start:  {data['start']}\n"
                f"Finish: {data['finish']}"
            )
            sel.annotation.get_bbox_patch().set(facecolor="lightyellow", alpha=0.9)

    except ImportError:
        pass  # mplcursors not installed — run: pip install mplcursors

    plt.tight_layout()
    if output_path:
        plt.savefig(output_path, dpi=150)
        print(f"Saved to {output_path}")
    else:
        plt.show()


def plot_from_json(path: str, output_path: str | None = None) -> None:
    """Load a solution JSON from *path* and display its Gantt chart."""
    with open(path, encoding="utf-8") as f:
        solution = json.load(f)
    plot_schedule(solution, output_path=output_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("solution", help="Path to solution JSON file")
    parser.add_argument("--output", help="Save plot to file instead of showing it")
    args = parser.parse_args()

    with open(args.solution) as f:
        solution = json.load(f)

    plot_schedule(solution, output_path=args.output)
