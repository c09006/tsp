"""
GUI benchmark runner for the mTSP simulator.

This window lets you enter benchmark parameters visually, run all combinations,
watch progress, and save the results as CSV.
"""

from __future__ import annotations

import csv
import queue
import re
import threading
import tkinter as tk
from itertools import product
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from benchmark_mtsp import (
    BENCHMARK_FIELDNAMES,
    DEFAULT_BUILDINGS,
    DEFAULT_INSPECTORS,
    DEFAULT_OUTPUT,
    DEFAULT_SEEDS,
    DEFAULT_TIME_LIMITS,
    run_single_case,
)
from mtsp_emergency_inspection import SPAN_COST_COEFFICIENT


def int_list_to_text(values: list[int]) -> str:
    """Format an integer list for an entry widget."""
    return " ".join(str(value) for value in values)


def parse_int_list(text: str, label: str, *, minimum: int) -> list[int]:
    """Parse integers separated by spaces, commas, or new lines."""
    parts = [part for part in re.split(r"[\s,]+", text.strip()) if part]
    if not parts:
        raise ValueError(f"{label}を1つ以上入力してください。")

    values: list[int] = []
    for part in parts:
        try:
            value = int(part)
        except ValueError as exc:
            raise ValueError(f"{label}には整数を入力してください: {part}") from exc

        if value < minimum:
            raise ValueError(f"{label}は{minimum}以上にしてください: {value}")

        values.append(value)

    return values


class BenchmarkGui(tk.Tk):
    """Small Tkinter app for mTSP benchmark experiments."""

    def __init__(self) -> None:
        super().__init__()

        self.title("mTSP ベンチマーク")
        self.geometry("900x700")
        self.minsize(820, 620)

        self.buildings_var = tk.StringVar(value=int_list_to_text(DEFAULT_BUILDINGS))
        self.inspectors_var = tk.StringVar(value=int_list_to_text(DEFAULT_INSPECTORS))
        self.time_limits_var = tk.StringVar(value=int_list_to_text(DEFAULT_TIME_LIMITS))
        self.seeds_var = tk.StringVar(value=int_list_to_text(DEFAULT_SEEDS))
        self.span_cost_var = tk.StringVar(value=str(SPAN_COST_COEFFICIENT))
        self.output_var = tk.StringVar(value=DEFAULT_OUTPUT)
        self.trace_memory_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="待機中")

        self.progress_queue: queue.Queue = queue.Queue()
        self.is_running = False

        self._build_widgets()

    def _build_widgets(self) -> None:
        root = ttk.Frame(self, padding=16)
        root.pack(fill=tk.BOTH, expand=True)

        settings = ttk.LabelFrame(root, text="ベンチマーク条件", padding=12)
        settings.pack(fill=tk.X)
        settings.columnconfigure(1, weight=1)

        self._add_entry(
            settings,
            "建物数",
            self.buildings_var,
            0,
            "例: 200 500 1000",
        )
        self._add_entry(
            settings,
            "判定士数",
            self.inspectors_var,
            1,
            "例: 3 5 10",
        )
        self._add_entry(
            settings,
            "探索時間（秒）",
            self.time_limits_var,
            2,
            "例: 10 30 60",
        )
        self._add_entry(
            settings,
            "乱数シード",
            self.seeds_var,
            3,
            "例: 42 43 44",
        )
        self._add_entry(
            settings,
            "偏り抑制係数",
            self.span_cost_var,
            4,
            "例: 100",
        )

        ttk.Label(settings, text="保存先CSV").grid(row=5, column=0, sticky=tk.W, pady=4)
        output_frame = ttk.Frame(settings)
        output_frame.grid(row=5, column=1, sticky=tk.EW, padx=(12, 0), pady=4)
        output_frame.columnconfigure(0, weight=1)

        self.output_entry = ttk.Entry(output_frame, textvariable=self.output_var)
        self.output_entry.grid(row=0, column=0, sticky=tk.EW)

        browse_button = ttk.Button(output_frame, text="参照", command=self.choose_output)
        browse_button.grid(row=0, column=1, padx=(8, 0))

        trace_check = ttk.Checkbutton(
            settings,
            text="Pythonメモリ使用量も計測する（大規模ケースでは遅くなることがあります）",
            variable=self.trace_memory_var,
        )
        trace_check.grid(row=6, column=0, columnspan=2, sticky=tk.W, pady=(8, 0))

        button_frame = ttk.Frame(root)
        button_frame.pack(fill=tk.X, pady=12)

        self.run_button = ttk.Button(button_frame, text="ベンチマーク開始", command=self.start_benchmark)
        self.run_button.pack(side=tk.LEFT)

        self.reset_button = ttk.Button(button_frame, text="初期値に戻す", command=self.reset_defaults)
        self.reset_button.pack(side=tk.LEFT, padx=8)

        self.case_count_label = ttk.Label(button_frame, text="")
        self.case_count_label.pack(side=tk.LEFT, padx=16)

        progress_frame = ttk.Frame(root)
        progress_frame.pack(fill=tk.X, pady=(0, 12))

        ttk.Label(progress_frame, textvariable=self.status_var).pack(anchor=tk.W)
        self.progress_bar = ttk.Progressbar(
            progress_frame,
            mode="determinate",
            maximum=100,
            value=0,
        )
        self.progress_bar.pack(fill=tk.X, pady=(4, 0))

        output = ttk.LabelFrame(root, text="実行ログ", padding=8)
        output.pack(fill=tk.BOTH, expand=True)

        self.output_text = scrolledtext.ScrolledText(
            output,
            wrap=tk.WORD,
            height=20,
            font=("Consolas", 10),
        )
        self.output_text.pack(fill=tk.BOTH, expand=True)

        self._write_output(
            "条件を入力して「ベンチマーク開始」を押してください。\n"
            "複数値はスペース、カンマ、改行で区切れます。"
        )
        self._refresh_case_count()

        for variable in [
            self.buildings_var,
            self.inspectors_var,
            self.time_limits_var,
            self.seeds_var,
        ]:
            variable.trace_add("write", lambda *_: self._refresh_case_count())

    def _add_entry(
        self,
        parent: ttk.Frame,
        label: str,
        variable: tk.StringVar,
        row: int,
        example: str,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky=tk.W, pady=4)
        entry = ttk.Entry(parent, textvariable=variable)
        entry.grid(row=row, column=1, sticky=tk.EW, padx=(12, 0), pady=4)
        ttk.Label(parent, text=example).grid(row=row, column=2, sticky=tk.W, padx=(8, 0), pady=4)

    def choose_output(self) -> None:
        """Ask the user for an output CSV path."""
        selected = filedialog.asksaveasfilename(
            title="保存先CSVを選択",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=Path(self.output_var.get()).name,
        )
        if selected:
            self.output_var.set(selected)

    def reset_defaults(self) -> None:
        """Reset form values."""
        if self.is_running:
            return

        self.buildings_var.set(int_list_to_text(DEFAULT_BUILDINGS))
        self.inspectors_var.set(int_list_to_text(DEFAULT_INSPECTORS))
        self.time_limits_var.set(int_list_to_text(DEFAULT_TIME_LIMITS))
        self.seeds_var.set(int_list_to_text(DEFAULT_SEEDS))
        self.span_cost_var.set(str(SPAN_COST_COEFFICIENT))
        self.output_var.set(DEFAULT_OUTPUT)
        self.trace_memory_var.set(False)
        self.status_var.set("待機中")
        self.progress_bar.configure(value=0)
        self._write_output("初期値に戻しました。")

    def start_benchmark(self) -> None:
        """Validate parameters and launch benchmark in a worker thread."""
        if self.is_running:
            return

        try:
            buildings = parse_int_list(self.buildings_var.get(), "建物数", minimum=1)
            inspectors = parse_int_list(self.inspectors_var.get(), "判定士数", minimum=1)
            time_limits = parse_int_list(self.time_limits_var.get(), "探索時間", minimum=1)
            seeds = parse_int_list(self.seeds_var.get(), "乱数シード", minimum=0)
            span_cost = int(self.span_cost_var.get())
            if span_cost < 0:
                raise ValueError("偏り抑制係数は0以上にしてください。")
        except ValueError as exc:
            messagebox.showerror("入力エラー", str(exc))
            return

        output_path = Path(self.output_var.get())
        if not output_path.name:
            messagebox.showerror("入力エラー", "保存先CSVを入力してください。")
            return

        cases = list(product(buildings, inspectors, time_limits, seeds))
        if not cases:
            messagebox.showerror("入力エラー", "実行する条件がありません。")
            return

        self._set_running(True)
        self.progress_bar.configure(value=0)
        self.status_var.set("ベンチマークを開始しています...")
        self._write_output(f"{len(cases)}ケースを実行します。\n保存先: {output_path}\n")

        while not self.progress_queue.empty():
            self.progress_queue.get_nowait()

        worker = threading.Thread(
            target=self._benchmark_worker,
            args=(cases, output_path, span_cost, self.trace_memory_var.get()),
            daemon=True,
        )
        worker.start()
        self.after(100, self._poll_progress_queue)

    def _benchmark_worker(
        self,
        cases: list[tuple[int, int, int, int]],
        output_path: Path,
        span_cost: int,
        trace_memory: bool,
    ) -> None:
        """Run benchmark cases and send progress to the GUI thread."""
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with output_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=BENCHMARK_FIELDNAMES)
                writer.writeheader()

                for case_index, (buildings, inspectors, time_limit, seed) in enumerate(
                    cases,
                    start=1,
                ):
                    progress = int((case_index - 1) / len(cases) * 100)
                    self.progress_queue.put(
                        (
                            "progress",
                            case_index,
                            len(cases),
                            progress,
                            buildings,
                            inspectors,
                            time_limit,
                            seed,
                        )
                    )

                    row = run_single_case(
                        buildings,
                        inspectors,
                        time_limit,
                        seed,
                        span_cost,
                        trace_memory,
                    )
                    writer.writerow(row)
                    csv_file.flush()

                    self.progress_queue.put(("row", case_index, len(cases), row))

            self.progress_queue.put(("done", output_path))
        except Exception as exc:
            self.progress_queue.put(("error", str(exc)))

    def _poll_progress_queue(self) -> None:
        """Process messages from the worker thread."""
        try:
            while True:
                message = self.progress_queue.get_nowait()
                message_type = message[0]

                if message_type == "progress":
                    (
                        _,
                        case_index,
                        total_cases,
                        progress,
                        buildings,
                        inspectors,
                        time_limit,
                        seed,
                    ) = message
                    self.progress_bar.configure(value=progress)
                    self.status_var.set(
                        f"{case_index}/{total_cases}: "
                        f"建物={buildings}, 判定士={inspectors}, "
                        f"探索={time_limit}秒, seed={seed}"
                    )

                elif message_type == "row":
                    _, case_index, total_cases, row = message
                    self.progress_bar.configure(value=int(case_index / total_cases * 100))
                    self._append_row_summary(case_index, total_cases, row)

                elif message_type == "done":
                    _, output_path = message
                    self.progress_bar.configure(value=100)
                    self.status_var.set("完了しました")
                    self._append_output(f"\n完了しました。CSV: {output_path}\n")
                    self._set_running(False)
                    return

                elif message_type == "error":
                    _, error_text = message
                    self.status_var.set("エラーが発生しました")
                    self._append_output(f"\nエラー: {error_text}\n")
                    self._set_running(False)
                    messagebox.showerror("エラー", error_text)
                    return
        except queue.Empty:
            pass

        self.after(100, self._poll_progress_queue)

    def _append_row_summary(
        self,
        case_index: int,
        total_cases: int,
        row: dict[str, object],
    ) -> None:
        if row.get("solution_found"):
            text = (
                f"[{case_index}/{total_cases}] solved "
                f"buildings={row.get('num_buildings')} "
                f"inspectors={row.get('num_inspectors')} "
                f"time={row.get('time_limit_seconds')} "
                f"seed={row.get('seed')} "
                f"max_distance={row.get('max_distance')} "
                f"imbalance={float(row.get('imbalance_ratio', 0)):.3f} "
                f"total_time={float(row.get('total_time_seconds', 0)):.3f}s\n"
            )
        else:
            text = (
                f"[{case_index}/{total_cases}] no solution/error "
                f"buildings={row.get('num_buildings')} "
                f"inspectors={row.get('num_inspectors')} "
                f"time={row.get('time_limit_seconds')} "
                f"seed={row.get('seed')} "
                f"error={row.get('error', '')}\n"
            )
        self._append_output(text)

    def _refresh_case_count(self) -> None:
        """Update the case count label from current inputs."""
        try:
            buildings = parse_int_list(self.buildings_var.get(), "建物数", minimum=1)
            inspectors = parse_int_list(self.inspectors_var.get(), "判定士数", minimum=1)
            time_limits = parse_int_list(self.time_limits_var.get(), "探索時間", minimum=1)
            seeds = parse_int_list(self.seeds_var.get(), "乱数シード", minimum=0)
            count = len(buildings) * len(inspectors) * len(time_limits) * len(seeds)
            self.case_count_label.configure(text=f"実行ケース数: {count}")
        except ValueError:
            self.case_count_label.configure(text="実行ケース数: -")

    def _set_running(self, is_running: bool) -> None:
        self.is_running = is_running
        state = tk.DISABLED if is_running else tk.NORMAL
        self.run_button.configure(state=state)
        self.reset_button.configure(state=state)

    def _write_output(self, text: str) -> None:
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert(tk.END, text)

    def _append_output(self, text: str) -> None:
        self.output_text.insert(tk.END, text)
        self.output_text.see(tk.END)


if __name__ == "__main__":
    app = BenchmarkGui()
    app.mainloop()
