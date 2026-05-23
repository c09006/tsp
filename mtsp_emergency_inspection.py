"""
OR-Toolsで解くmTSPハンズオン:
応急危険度判定における複数判定士の巡回ルート最適化

README風メモ
============

1. 依存ライブラリのインストール

   WindowsのPowerShellまたはコマンドプロンプトで、次を実行してください。

       py -m pip install ortools matplotlib

   もし `py` が使えない場合は、次でも構いません。

       python -m pip install ortools matplotlib

2. 実行方法

       py mtsp_emergency_inspection.py

   または

       python mtsp_emergency_inspection.py

3. このコードで行うこと

   - 0番地点を「災害対策本部」とします。
   - 1〜20番地点を「判定対象建物」とします。
   - 3人の判定士が本部から出発し、本部へ戻ります。
   - すべての建物を必ず1回だけ訪問します。
   - OR-ToolsのRouting SolverでmTSPとして解きます。
   - 各判定士の移動距離をなるべく偏らせないため、
     「最長ルートを短くする」目的も入れます。
   - GUIでパラメータを設定できます。
   - matplotlibで巡回経路を図示します。

注意
====

このコードは初学者向けのシミュレーションです。現実の応急危険度判定では、
道路閉塞、橋梁被害、判定士の経験差、建物の危険度、調査時間、余震リスクなども
考慮する必要があります。
"""

import math
import random
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

import matplotlib.pyplot as plt
from ortools.constraint_solver import pywrapcp, routing_enums_pb2


# -----------------------------
# 変更しやすい設定値
# -----------------------------

RANDOM_SEED = 42
NUM_BUILDINGS = 20
NUM_INSPECTORS = 3
DEPOT_INDEX = 0
TIME_LIMIT_SECONDS = 10
SPAN_COST_COEFFICIENT = 100

# matplotlibのフォント設定です。
# WindowsならMeiryoが入っていることが多いため、日本語表示用に指定します。
# 環境にない場合でも、英数字部分は表示されます。
plt.rcParams["font.family"] = "Meiryo"


def generate_locations(num_buildings, seed=42):
    """本部と判定対象建物の仮想座標をランダムに生成する。

    戻り値:
        locations: [(x, y), ...]

    0番地点を災害対策本部とし、座標は中心付近に固定します。
    1番以降の建物座標はランダムに生成します。
    """
    random.seed(seed)

    locations = []

    # 0番地点: 災害対策本部
    locations.append((50, 50))

    # 1〜20番地点: 判定対象建物
    for _ in range(num_buildings):
        x = random.randint(5, 95)
        y = random.randint(5, 95)
        locations.append((x, y))

    return locations


def euclidean_distance(point_a, point_b):
    """2点間のユークリッド距離を計算する。

    OR-ToolsのRouting Solverでは距離を整数として扱うのが簡単なので、
    小数ではなく四捨五入した整数距離を返します。
    """
    return int(round(math.hypot(point_a[0] - point_b[0], point_a[1] - point_b[1])))


def create_distance_matrix(locations):
    """全地点間の距離行列を作成する。

    distance_matrix[i][j] は、
    i番地点からj番地点へ移動する距離を表します。
    """
    distance_matrix = []

    for from_location in locations:
        row = []
        for to_location in locations:
            row.append(euclidean_distance(from_location, to_location))
        distance_matrix.append(row)

    return distance_matrix


def solve_mtsp(
    distance_matrix,
    num_inspectors,
    depot_index,
    time_limit_seconds,
    span_cost_coefficient,
):
    """OR-ToolsでmTSPを解く。

    mTSPは、OR-ToolsのVehicle Routing Problemとして表現できます。
    ここでは「判定士 = 車両」と考えます。

    Args:
        distance_matrix: 地点間距離の2次元リスト
        num_inspectors: 判定士の人数
        depot_index: 出発・帰着地点、つまり災害対策本部の地点番号
        time_limit_seconds: 探索に使う最大秒数
        span_cost_coefficient: 最長ルートを短くする圧力の強さ

    Returns:
        manager: OR-Tools内部のインデックス変換を管理するオブジェクト
        routing: ルーティング問題のモデル
        solution: 求解結果
    """
    # RoutingIndexManagerは、
    # 「地点番号」と「OR-Tools内部で使うインデックス」を対応させます。
    manager = pywrapcp.RoutingIndexManager(
        len(distance_matrix),
        num_inspectors,
        depot_index,
    )

    # RoutingModelが、巡回経路最適化の本体です。
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        """OR-Toolsが経路評価時に呼び出す距離関数。

        from_index/to_indexはOR-Tools内部のインデックスなので、
        manager.IndexToNodeで元の地点番号に戻してから距離行列を参照します。
        """
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return distance_matrix[from_node][to_node]

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)

    # すべての移動コストを距離として設定します。
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    # 「距離」というDimensionを追加します。
    # Dimensionを使うと、各判定士の累積移動距離を制約や目的関数に使えます。
    routing.AddDimension(
        transit_callback_index,
        0,       # slack: 待ち時間のような余裕。今回は不要なので0。
        10_000,  # 各判定士の最大移動距離の上限。十分大きい値にします。
        True,    # 出発地点での累積距離を0に固定します。
        "Distance",
    )

    distance_dimension = routing.GetDimensionOrDie("Distance")

    # ここが「1人にルートが偏りすぎないようにする」ための重要ポイントです。
    #
    # SetGlobalSpanCostCoefficientは、
    # 各判定士のルート距離のうち「最大値」を小さくする圧力を加えます。
    # つまり、総距離だけを短くするのではなく、
    # 最も長く働く判定士の負担をなるべく軽くする方向に解を探します。
    distance_dimension.SetGlobalSpanCostCoefficient(span_cost_coefficient)

    # 探索方法を設定します。
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()

    # 最初の実行可能解を作る方法です。
    # PATH_CHEAPEST_ARCは初学者向けの例でよく使われる、分かりやすい設定です。
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )

    # 初期解を改善するための局所探索手法です。
    search_parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )

    # ハンズオンで待ちすぎないように、探索時間を短めに制限します。
    search_parameters.time_limit.FromSeconds(time_limit_seconds)

    # ログを見たい場合はTrueにします。
    search_parameters.log_search = False

    solution = routing.SolveWithParameters(search_parameters)

    return manager, routing, solution


def extract_routes(manager, routing, solution, num_inspectors):
    """OR-Toolsの解から、判定士ごとのルートと距離を取り出す。"""
    routes = []

    for inspector_id in range(num_inspectors):
        index = routing.Start(inspector_id)
        route = []
        route_distance = 0

        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            route.append(node)

            previous_index = index
            index = solution.Value(routing.NextVar(index))
            route_distance += routing.GetArcCostForVehicle(
                previous_index,
                index,
                inspector_id,
            )

        # 最後に本部へ戻る終点もルートに追加します。
        route.append(manager.IndexToNode(index))

        routes.append(
            {
                "inspector_id": inspector_id + 1,
                "route": route,
                "distance": route_distance,
            }
        )

    return routes


def build_routes_report(routes):
    """判定士ごとの担当ルートと移動距離を、表示用テキストとして作成する。"""
    lines = []
    lines.append("=== mTSP計算結果: 応急危険度判定ルート ===")

    total_distance = 0
    max_distance = 0

    for route_info in routes:
        inspector_id = route_info["inspector_id"]
        route = route_info["route"]
        distance = route_info["distance"]

        total_distance += distance
        max_distance = max(max_distance, distance)

        route_text = " -> ".join(str(node) for node in route)

        lines.append("")
        lines.append(f"判定士 {inspector_id}")
        lines.append(f"  担当ルート: {route_text}")
        lines.append(f"  移動距離  : {distance}")

    lines.append("")
    lines.append("--- 集計 ---")
    lines.append(f"総移動距離      : {total_distance}")
    lines.append(f"最長ルート距離  : {max_distance}")
    lines.append("※最長ルート距離を短くすることで、担当の偏りを抑えています。")

    return "\n".join(lines)


def print_routes(routes):
    """判定士ごとの担当ルートと移動距離を表示する。"""
    print("\n" + build_routes_report(routes))


def plot_routes(locations, routes):
    """matplotlibで巡回経路を可視化する。"""
    plt.figure(figsize=(10, 8))

    # 建物と本部の座標を分けて描画します。
    depot_x, depot_y = locations[DEPOT_INDEX]
    building_x = [locations[i][0] for i in range(1, len(locations))]
    building_y = [locations[i][1] for i in range(1, len(locations))]

    plt.scatter(building_x, building_y, c="steelblue", s=80, label="判定対象建物")
    plt.scatter(depot_x, depot_y, c="crimson", s=220, marker="*", label="災害対策本部")

    # 各地点に番号を表示します。
    for node_id, (x, y) in enumerate(locations):
        if node_id == DEPOT_INDEX:
            plt.text(x + 1.2, y + 1.2, "0 本部", fontsize=10, weight="bold")
        else:
            plt.text(x + 1.2, y + 1.2, str(node_id), fontsize=9)

    # 判定士ごとに色を変えてルートを描画します。
    color_map = plt.get_cmap("tab10")

    for route_index, route_info in enumerate(routes):
        color = color_map(route_index % 10)
        route = route_info["route"]
        inspector_id = route_info["inspector_id"]
        distance = route_info["distance"]

        route_x = [locations[node][0] for node in route]
        route_y = [locations[node][1] for node in route]

        plt.plot(
            route_x,
            route_y,
            color=color,
            linewidth=2.5,
            marker="o",
            markersize=5,
            label=f"判定士{inspector_id}: 距離 {distance}",
        )

        # 進行方向が分かるように、各区間に薄い矢印を描きます。
        for start_node, end_node in zip(route[:-1], route[1:]):
            start_x, start_y = locations[start_node]
            end_x, end_y = locations[end_node]
            dx = end_x - start_x
            dy = end_y - start_y

            plt.arrow(
                start_x,
                start_y,
                dx * 0.75,
                dy * 0.75,
                color=color,
                alpha=0.35,
                head_width=1.5,
                length_includes_head=True,
            )

    plt.title("応急危険度判定 mTSP シミュレーション")
    plt.xlabel("X座標")
    plt.ylabel("Y座標")
    plt.xlim(0, 100)
    plt.ylim(0, 100)
    plt.grid(True, linestyle="--", alpha=0.4)
    plt.legend()
    plt.tight_layout()
    plt.show()


def main():
    """GUIを使わず、固定パラメータで実行する関数。"""
    locations = generate_locations(NUM_BUILDINGS, RANDOM_SEED)
    distance_matrix = create_distance_matrix(locations)

    manager, routing, solution = solve_mtsp(
        distance_matrix,
        NUM_INSPECTORS,
        DEPOT_INDEX,
        TIME_LIMIT_SECONDS,
        SPAN_COST_COEFFICIENT,
    )

    if solution is None:
        print("解が見つかりませんでした。設定値や制約を見直してください。")
        return

    routes = extract_routes(manager, routing, solution, NUM_INSPECTORS)
    print_routes(routes)
    plot_routes(locations, routes)


class MtspGui(tk.Tk):
    """パラメータを入力してmTSPを実行する簡単なGUI。"""

    def __init__(self):
        super().__init__()

        self.title("応急危険度判定 mTSP シミュレーター")
        self.geometry("760x620")
        self.minsize(700, 560)

        self.seed_var = tk.StringVar(value=str(RANDOM_SEED))
        self.buildings_var = tk.StringVar(value=str(NUM_BUILDINGS))
        self.inspectors_var = tk.StringVar(value=str(NUM_INSPECTORS))
        self.time_limit_var = tk.StringVar(value=str(TIME_LIMIT_SECONDS))
        self.span_cost_var = tk.StringVar(value=str(SPAN_COST_COEFFICIENT))
        self.show_plot_var = tk.BooleanVar(value=True)

        self._build_widgets()

    def _build_widgets(self):
        """GUI部品を配置する。"""
        root_frame = ttk.Frame(self, padding=16)
        root_frame.pack(fill=tk.BOTH, expand=True)

        settings_frame = ttk.LabelFrame(root_frame, text="パラメータ設定", padding=12)
        settings_frame.pack(fill=tk.X)

        self._add_entry(settings_frame, "乱数シード", self.seed_var, 0)
        self._add_entry(settings_frame, "判定対象建物数", self.buildings_var, 1)
        self._add_entry(settings_frame, "判定士数", self.inspectors_var, 2)
        self._add_entry(settings_frame, "探索時間（秒）", self.time_limit_var, 3)
        self._add_entry(settings_frame, "偏り抑制係数", self.span_cost_var, 4)

        plot_check = ttk.Checkbutton(
            settings_frame,
            text="実行後に経路図を表示する",
            variable=self.show_plot_var,
        )
        plot_check.grid(row=5, column=0, columnspan=2, sticky=tk.W, pady=(10, 0))

        button_frame = ttk.Frame(root_frame)
        button_frame.pack(fill=tk.X, pady=12)

        run_button = ttk.Button(button_frame, text="ルートを計算", command=self.run_solver)
        run_button.pack(side=tk.LEFT)

        reset_button = ttk.Button(button_frame, text="初期値に戻す", command=self.reset_defaults)
        reset_button.pack(side=tk.LEFT, padx=8)

        output_frame = ttk.LabelFrame(root_frame, text="実行結果", padding=8)
        output_frame.pack(fill=tk.BOTH, expand=True)

        self.output_text = scrolledtext.ScrolledText(
            output_frame,
            wrap=tk.WORD,
            height=18,
            font=("Consolas", 10),
        )
        self.output_text.pack(fill=tk.BOTH, expand=True)

        self._write_output(
            "パラメータを設定して「ルートを計算」を押してください。\n"
            "偏り抑制係数を大きくすると、最長ルートを短くする力が強くなります。"
        )

    def _add_entry(self, parent, label, variable, row):
        """ラベルと入力欄を1行追加する。"""
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky=tk.W, pady=4)
        entry = ttk.Entry(parent, textvariable=variable, width=16)
        entry.grid(row=row, column=1, sticky=tk.W, padx=(12, 0), pady=4)

    def _read_positive_int(self, variable, label, minimum=1, maximum=None):
        """入力欄から正の整数を読み取る。範囲外なら分かりやすいエラーにする。"""
        try:
            value = int(variable.get())
        except ValueError as exc:
            raise ValueError(f"{label}は整数で入力してください。") from exc

        if value < minimum:
            raise ValueError(f"{label}は{minimum}以上にしてください。")

        if maximum is not None and value > maximum:
            raise ValueError(f"{label}は{maximum}以下にしてください。")

        return value

    def run_solver(self):
        """GUIで入力されたパラメータを使ってmTSPを解く。"""
        try:
            seed = self._read_positive_int(self.seed_var, "乱数シード", minimum=0)
            num_buildings = self._read_positive_int(
                self.buildings_var,
                "判定対象建物数",
                minimum=1,
                maximum=200,
            )
            num_inspectors = self._read_positive_int(
                self.inspectors_var,
                "判定士数",
                minimum=1,
                maximum=30,
            )
            time_limit_seconds = self._read_positive_int(
                self.time_limit_var,
                "探索時間",
                minimum=1,
                maximum=300,
            )
            span_cost_coefficient = self._read_positive_int(
                self.span_cost_var,
                "偏り抑制係数",
                minimum=0,
                maximum=10_000,
            )
        except ValueError as exc:
            messagebox.showerror("入力エラー", str(exc))
            return

        self._write_output("計算中です...")
        self.update_idletasks()

        locations = generate_locations(num_buildings, seed)
        distance_matrix = create_distance_matrix(locations)

        manager, routing, solution = solve_mtsp(
            distance_matrix,
            num_inspectors,
            DEPOT_INDEX,
            time_limit_seconds,
            span_cost_coefficient,
        )

        if solution is None:
            messagebox.showwarning("結果", "解が見つかりませんでした。設定値や制約を見直してください。")
            self._write_output("解が見つかりませんでした。")
            return

        routes = extract_routes(manager, routing, solution, num_inspectors)
        report = build_routes_report(routes)

        parameter_report = (
            f"乱数シード      : {seed}\n"
            f"判定対象建物数  : {num_buildings}\n"
            f"判定士数        : {num_inspectors}\n"
            f"探索時間（秒）  : {time_limit_seconds}\n"
            f"偏り抑制係数    : {span_cost_coefficient}\n\n"
        )

        self._write_output(parameter_report + report)

        if self.show_plot_var.get():
            plot_routes(locations, routes)

    def reset_defaults(self):
        """入力値を初期値に戻す。"""
        self.seed_var.set(str(RANDOM_SEED))
        self.buildings_var.set(str(NUM_BUILDINGS))
        self.inspectors_var.set(str(NUM_INSPECTORS))
        self.time_limit_var.set(str(TIME_LIMIT_SECONDS))
        self.span_cost_var.set(str(SPAN_COST_COEFFICIENT))
        self.show_plot_var.set(True)

    def _write_output(self, text):
        """結果表示欄を書き換える。"""
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert(tk.END, text)


if __name__ == "__main__":
    app = MtspGui()
    app.mainloop()
