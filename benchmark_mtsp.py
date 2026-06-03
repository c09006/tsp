"""
mTSP benchmark runner.

This script runs the OR-Tools mTSP simulator many times without plotting and
writes performance metrics to a CSV file.

Example:

    py benchmark_mtsp.py --buildings 200 500 1000 --inspectors 3 5 10 --time-limits 10 30 --seeds 42 43

For large experiments, keep plotting disabled and compare:

- solution_found
- total_distance
- max_distance
- imbalance_ratio
- matrix_time_seconds
- solve_time_seconds
- total_time_seconds
"""

from __future__ import annotations

import argparse
import csv
import statistics
import time
import tracemalloc
from itertools import product
from pathlib import Path

from mtsp_emergency_inspection import (
    DEPOT_INDEX,
    SPAN_COST_COEFFICIENT,
    create_distance_matrix,
    extract_routes,
    generate_locations,
    solve_mtsp,
)


DEFAULT_BUILDINGS = [200, 500, 1000]
DEFAULT_INSPECTORS = [3, 5, 10]
DEFAULT_TIME_LIMITS = [10, 30]
DEFAULT_SEEDS = [42]
DEFAULT_OUTPUT = "benchmark_results.csv"
BENCHMARK_FIELDNAMES = [
    "num_buildings",
    "num_locations",
    "num_inspectors",
    "time_limit_seconds",
    "seed",
    "span_cost_coefficient",
    "solution_found",
    "generate_time_seconds",
    "matrix_time_seconds",
    "solve_time_seconds",
    "extract_time_seconds",
    "total_time_seconds",
    "setup_time_seconds",
    "non_solver_time_seconds",
    "solve_overrun_seconds",
    "solve_time_ratio",
    "total_distance",
    "max_distance",
    "min_distance",
    "avg_distance",
    "imbalance_ratio",
    "max_buildings_per_inspector",
    "min_buildings_per_inspector",
    "avg_buildings_per_inspector",
    "tracemalloc_current_mb",
    "tracemalloc_peak_mb",
    "error",
]


def positive_int(value: str) -> int:
    """argparse helper for positive integers."""
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def non_negative_int(value: str) -> int:
    """argparse helper for non-negative integers."""
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be a non-negative integer")
    return parsed


def route_metrics(routes: list[dict[str, object]]) -> dict[str, float | int]:
    """Compute summary metrics from solved routes."""
    distances = [int(route["distance"]) for route in routes]
    building_counts = [
        sum(1 for node in route["route"] if int(node) != DEPOT_INDEX)
        for route in routes
    ]

    total_distance = sum(distances)
    max_distance = max(distances) if distances else 0
    min_distance = min(distances) if distances else 0
    avg_distance = statistics.mean(distances) if distances else 0
    imbalance_ratio = max_distance / avg_distance if avg_distance else 0

    return {
        "total_distance": total_distance,
        "max_distance": max_distance,
        "min_distance": min_distance,
        "avg_distance": avg_distance,
        "imbalance_ratio": imbalance_ratio,
        "max_buildings_per_inspector": max(building_counts) if building_counts else 0,
        "min_buildings_per_inspector": min(building_counts) if building_counts else 0,
        "avg_buildings_per_inspector": statistics.mean(building_counts)
        if building_counts
        else 0,
    }


def run_single_case(
    num_buildings: int,
    num_inspectors: int,
    time_limit_seconds: int,
    seed: int,
    span_cost_coefficient: int,
    trace_memory: bool,
) -> dict[str, object]:
    """Run one benchmark case and return one CSV row."""
    if trace_memory:
        tracemalloc.start()

    total_start = time.perf_counter()

    row: dict[str, object] = {
        "num_buildings": num_buildings,
        "num_locations": num_buildings + 1,
        "num_inspectors": num_inspectors,
        "time_limit_seconds": time_limit_seconds,
        "seed": seed,
        "span_cost_coefficient": span_cost_coefficient,
        "solution_found": False,
    }

    try:
        start = time.perf_counter()
        locations = generate_locations(num_buildings, seed)
        row["generate_time_seconds"] = time.perf_counter() - start

        start = time.perf_counter()
        distance_matrix = create_distance_matrix(locations)
        row["matrix_time_seconds"] = time.perf_counter() - start

        start = time.perf_counter()
        manager, routing, solution = solve_mtsp(
            distance_matrix,
            num_inspectors,
            DEPOT_INDEX,
            time_limit_seconds,
            span_cost_coefficient,
        )
        row["solve_time_seconds"] = time.perf_counter() - start

        if solution is not None:
            row["solution_found"] = True

            start = time.perf_counter()
            routes = extract_routes(manager, routing, solution, num_inspectors)
            row["extract_time_seconds"] = time.perf_counter() - start
            row.update(route_metrics(routes))
        else:
            row["extract_time_seconds"] = 0.0

        row["error"] = ""
    except Exception as exc:
        row["error"] = str(exc)
    finally:
        generate_time = float(row.get("generate_time_seconds", 0) or 0)
        matrix_time = float(row.get("matrix_time_seconds", 0) or 0)
        solve_time = float(row.get("solve_time_seconds", 0) or 0)
        extract_time = float(row.get("extract_time_seconds", 0) or 0)

        row["setup_time_seconds"] = generate_time + matrix_time
        row["non_solver_time_seconds"] = generate_time + matrix_time + extract_time
        row["solve_overrun_seconds"] = solve_time - time_limit_seconds
        row["solve_time_ratio"] = (
            solve_time / time_limit_seconds if time_limit_seconds else ""
        )

        if trace_memory:
            current_bytes, peak_bytes = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            row["tracemalloc_current_mb"] = current_bytes / (1024 * 1024)
            row["tracemalloc_peak_mb"] = peak_bytes / (1024 * 1024)
        else:
            row["tracemalloc_current_mb"] = ""
            row["tracemalloc_peak_mb"] = ""

        row["total_time_seconds"] = time.perf_counter() - total_start

    return row


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run mTSP benchmark cases and write metrics to CSV.",
    )
    parser.add_argument(
        "--buildings",
        nargs="+",
        type=positive_int,
        default=DEFAULT_BUILDINGS,
        help="Building counts to test. Default: 200 500 1000",
    )
    parser.add_argument(
        "--inspectors",
        nargs="+",
        type=positive_int,
        default=DEFAULT_INSPECTORS,
        help="Inspector counts to test. Default: 3 5 10",
    )
    parser.add_argument(
        "--time-limits",
        nargs="+",
        type=positive_int,
        default=DEFAULT_TIME_LIMITS,
        help="OR-Tools time limits in seconds. Default: 10 30",
    )
    parser.add_argument(
        "--seeds",
        nargs="+",
        type=non_negative_int,
        default=DEFAULT_SEEDS,
        help="Random seeds to test. Default: 42",
    )
    parser.add_argument(
        "--span-cost",
        type=non_negative_int,
        default=SPAN_COST_COEFFICIENT,
        help=f"Global span cost coefficient. Default: {SPAN_COST_COEFFICIENT}",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(DEFAULT_OUTPUT),
        help=f"Output CSV path. Default: {DEFAULT_OUTPUT}",
    )
    parser.add_argument(
        "--trace-memory",
        action="store_true",
        help="Measure Python memory with tracemalloc. This can slow large cases.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cases = list(
        product(
            args.buildings,
            args.inspectors,
            args.time_limits,
            args.seeds,
        )
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)

    with args.output.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=BENCHMARK_FIELDNAMES)
        writer.writeheader()

        for case_index, (buildings, inspectors, time_limit, seed) in enumerate(
            cases,
            start=1,
        ):
            print(
                f"[{case_index}/{len(cases)}] "
                f"buildings={buildings}, inspectors={inspectors}, "
                f"time_limit={time_limit}, seed={seed}",
                flush=True,
            )
            row = run_single_case(
                buildings,
                inspectors,
                time_limit,
                seed,
                args.span_cost,
                args.trace_memory,
            )
            writer.writerow(row)
            csv_file.flush()

            if row.get("solution_found"):
                print(
                    "  solved: "
                    f"max_distance={row.get('max_distance')}, "
                    f"imbalance={float(row.get('imbalance_ratio', 0)):.3f}, "
                    f"non_solver_time={float(row.get('non_solver_time_seconds', 0)):.3f}s, "
                    f"wall_time={float(row.get('total_time_seconds', 0)):.3f}s",
                    flush=True,
                )
            else:
                print(
                    f"  no solution or error: {row.get('error', '')}",
                    flush=True,
                )

    print(f"\nBenchmark results written to: {args.output}")


if __name__ == "__main__":
    main()
