"""
OR-Toolsで解く mTSP ハンズオン:
応急危険度判定で、複数の判定士が建物を分担して巡回する例

============================================================
実行前の準備
============================================================

1. Python 3.10 以上を推奨します。

2. 必要なライブラリをインストールします。

   Windows PowerShell またはコマンドプロンプトで、このファイルがある
   フォルダに移動してから、次を実行してください。

   pip install ortools matplotlib

   もし複数のPythonが入っていて pip がうまく動かない場合は、
   次のように実行すると安定しやすいです。

   py -m pip install ortools matplotlib

3. このファイルを実行します。

   python mtsp_emergency_assessment.py

   または Windows では次も使えます。

   py mtsp_emergency_assessment.py

============================================================
このコードでしていること
============================================================

- 0番地点を「災害対策本部」とします。
- 1〜20番地点を「判定対象建物」とします。
- 判定士は3人です。
- 各判定士は本部から出発し、本部へ戻ります。
- 全ての建物を必ず1回だけ訪問します。
- 1人に担当が偏りすぎないように、各ルート距離の最大値を小さくする
  目的関数を使います。
- 最後に、各判定士のルートと距離を表示し、matplotlibで経路図を描きます。

============================================================
研究へ発展させるための改造ポイント
============================================================

- 建物ごとに「危険度」「調査時間」「優先度」を持たせる。
- 道路閉塞を想定して、直線距離ではなく道路ネットワーク距離を使う。
- 判定士ごとの経験値や移動速度の違いを入れる。
- 指定時間内に戻る制約、休憩、担当区域の制約を加える。
- 建物を必ず全件回るのではなく、優先度の高い建物を多く回る問題にする。
- 地図データやGIS座標と連携し、実際の市街地に近いシミュレーションにする。
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass

import matplotlib.pyplot as plt
from ortools.constraint_solver import pywrapcp, routing_enums_pb2


# ============================================================
# 基本設定
# ============================================================

# 乱数の種です。
# 同じ値にしておくと、毎回同じ仮想座標が作られるため、
# ハンズオンや説明で結果を再現しやすくなります。
RANDOM_SEED = 42

# 地点数です。
# 0番地点が本部、1〜20番地点が判定対象建物なので、合計21地点です。
NUM_BUILDINGS = 20
NUM_LOCATIONS = NUM_BUILDINGS + 1

# 判定士の人数です。
NUM_INSPECTORS = 3

# 本部の地点番号です。
DEPOT_INDEX = 0

# 仮想的な平面座標の範囲です。
# 100 x 100 の街区をイメージしています。
MAP_SIZE = 100

# OR-Toolsの探索時間の上限です。
# 大規模な実験では 60, 300, 1800 などに変更して比較します。
SOLVER_TIME_LIMIT_SECONDS = 10


@dataclass(frozen=True)
class Location:
    """地点情報を表す小さなデータ型です。"""

    index: int
    x: float
    y: float
    name: str


def generate_locations() -> list[Location]:
    """本部と判定対象建物の仮想座標をランダムに作ります。

    ここでは説明を簡単にするため、道路距離ではなく2次元平面上の
    ユークリッド距離を使います。
    """

    random.seed(RANDOM_SEED)

    locations: list[Location] = []

    # 0番地点は災害対策本部です。
    # 図の中央付近に固定しておくと、ルートが見やすくなります。
    locations.append(
        Location(
            index=DEPOT_INDEX,
            x=MAP_SIZE / 2,
            y=MAP_SIZE / 2,
            name="災害対策本部",
        )
    )

    # 1〜20番地点は、判定対象建物としてランダムに配置します。
    for i in range(1, NUM_LOCATIONS):
        locations.append(
            Location(
                index=i,
                x=random.uniform(0, MAP_SIZE),
                y=random.uniform(0, MAP_SIZE),
                name=f"建物{i}",
            )
        )

    return locations


def create_distance_matrix(locations: list[Location]) -> list[list[int]]:
    """地点間の距離行列を作ります。

    OR-ToolsのRoutingModelでは、距離や時間などのコストは整数で扱うのが
    一般的です。そのため、ここでは小数の距離を四捨五入して整数にします。
    """

    matrix: list[list[int]] = []

    for from_location in locations:
        row: list[int] = []
        for to_location in locations:
            dx = from_location.x - to_location.x
            dy = from_location.y - to_location.y
            distance = math.sqrt(dx * dx + dy * dy)
            row.append(int(round(distance)))
        matrix.append(row)

    return matrix


def solve_mtsp(distance_matrix: list[list[int]]) -> tuple[pywrapcp.RoutingModel, pywrapcp.RoutingIndexManager, object] | None:
    """OR-ToolsでmTSPを解きます。

    mTSPは「複数台の車両がある配送計画問題」として表現できます。
    ここでは、車両 = 判定士 と考えます。
    """

    # RoutingIndexManagerは、私たちが使う地点番号と、
    # OR-Tools内部で使うインデックスを変換するための管理役です。
    manager = pywrapcp.RoutingIndexManager(
        len(distance_matrix),
        NUM_INSPECTORS,
        DEPOT_INDEX,
    )

    # RoutingModelが、経路最適化問題の本体です。
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index: int, to_index: int) -> int:
        """OR-Toolsから呼ばれる距離計算関数です。

        from_index/to_index はOR-Tools内部の番号なので、
        manager.IndexToNode() で元の地点番号に戻してから距離表を参照します。
        """

        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return distance_matrix[from_node][to_node]

    # 距離計算関数をOR-Toolsに登録します。
    transit_callback_index = routing.RegisterTransitCallback(distance_callback)

    # 各移動のコストとして距離を使います。
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    # ------------------------------------------------------------
    # ルートの偏りを抑える設定
    # ------------------------------------------------------------
    # Distanceという「累積距離」を表すDimensionを追加します。
    #
    # 第4引数の True は、各判定士の出発時点の累積距離を0に固定する意味です。
    # 第5引数の "Distance" は、このDimensionの名前です。
    #
    # 第3引数は各ルートの距離上限です。
    # ここでは十分大きい値にしておき、厳しすぎて解が出ないことを避けます。
    routing.AddDimension(
        transit_callback_index,
        0,       # 移動距離に余裕値を加えない
        10_000,  # 各判定士の最大移動距離の上限
        True,    # 出発時の累積距離を0にする
        "Distance",
    )

    distance_dimension = routing.GetDimensionOrDie("Distance")

    # ここが「1人に偏りすぎない」ための重要な設定です。
    # GlobalSpanCostCoefficientを設定すると、
    # 全判定士の中で最も長いルートを短くする方向に最適化されます。
    #
    # 値を大きくすると、全体距離の短さよりもルート均等化を強く重視します。
    distance_dimension.SetGlobalSpanCostCoefficient(100)

    # ------------------------------------------------------------
    # 探索方法の設定
    # ------------------------------------------------------------
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()

    # 最初の解を作る方法です。
    # PATH_CHEAPEST_ARCは近い地点をつなぎながら初期解を作る、
    # 初学者にも理解しやすい代表的な方法です。
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )

    # 初期解を改善する方法です。
    # GUIDED_LOCAL_SEARCHは、巡回・配送問題でよく使われる改善手法です。
    search_parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )

    # ハンズオンで待ち時間が長くなりすぎないように、探索時間を制限します。
    search_parameters.time_limit.seconds = SOLVER_TIME_LIMIT_SECONDS

    # 解を探索します。
    solution = routing.SolveWithParameters(search_parameters)

    if solution is None:
        return None

    return routing, manager, solution


def extract_routes(
    routing: pywrapcp.RoutingModel,
    manager: pywrapcp.RoutingIndexManager,
    solution: object,
) -> list[dict[str, object]]:
    """OR-Toolsの解から、判定士ごとのルートと距離を取り出します。"""

    routes: list[dict[str, object]] = []

    for inspector_id in range(NUM_INSPECTORS):
        index = routing.Start(inspector_id)
        route: list[int] = []
        route_distance = 0

        # 終点に到達するまで、次の地点をたどります。
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


def print_routes(routes: list[dict[str, object]]) -> None:
    """判定士ごとの担当ルートと距離を表示します。"""

    print("\n=== 応急危険度判定 mTSP 結果 ===")
    print(f"判定士数: {NUM_INSPECTORS}人")
    print(f"判定対象建物数: {NUM_BUILDINGS}棟")
    print("0番地点: 災害対策本部")
    print()

    total_distance = 0
    max_distance = 0

    for route_info in routes:
        inspector_id = route_info["inspector_id"]
        route = route_info["route"]
        distance = route_info["distance"]

        route_text = " -> ".join(str(node) for node in route)

        print(f"判定士{inspector_id}の担当ルート:")
        print(f"  {route_text}")
        print(f"  移動距離: {distance}")
        print()

        total_distance += int(distance)
        max_distance = max(max_distance, int(distance))

    print(f"全判定士の合計移動距離: {total_distance}")
    print(f"最長ルート距離: {max_distance}")


def print_timing_report(timings: dict[str, float]) -> None:
    """処理ごとの実行時間を表示します。"""

    print()
    print("=== 実行時間 ===")
    print(f"地点生成: {timings['generate_locations']:.3f} 秒")
    print(f"距離行列作成: {timings['create_distance_matrix']:.3f} 秒")
    print(f"OR-Tools最適化: {timings['solve_mtsp']:.3f} 秒")
    print(f"結果抽出: {timings['extract_routes']:.3f} 秒")
    print(f"描画前までの合計: {timings['total_before_plot']:.3f} 秒")
    print()
    print(f"OR-Tools探索時間上限: {SOLVER_TIME_LIMIT_SECONDS} 秒")


def plot_routes(locations: list[Location], routes: list[dict[str, object]]) -> None:
    """matplotlibで地点とルートを可視化します。"""

    # 日本語フォントは環境によって異なります。
    # Windowsでは Yu Gothic が使えることが多いので指定します。
    # 使えない環境でも、グラフ自体は表示されます。
    plt.rcParams["font.family"] = ["Yu Gothic", "Meiryo", "MS Gothic", "sans-serif"]

    colors = ["tab:blue", "tab:orange", "tab:green"]

    plt.figure(figsize=(10, 8))

    # まず全ての地点を描画します。
    for location in locations:
        if location.index == DEPOT_INDEX:
            plt.scatter(
                location.x,
                location.y,
                c="red",
                s=180,
                marker="s",
                label="災害対策本部",
                zorder=3,
            )
        else:
            plt.scatter(
                location.x,
                location.y,
                c="black",
                s=60,
                marker="o",
                zorder=3,
            )

        # 地点番号を表示します。
        plt.text(
            location.x + 1,
            location.y + 1,
            str(location.index),
            fontsize=10,
        )

    # 判定士ごとのルートを線で結びます。
    for route_info in routes:
        inspector_id = int(route_info["inspector_id"])
        route = route_info["route"]
        color = colors[(inspector_id - 1) % len(colors)]

        x_values = [locations[node].x for node in route]
        y_values = [locations[node].y for node in route]

        plt.plot(
            x_values,
            y_values,
            color=color,
            linewidth=2,
            marker="o",
            label=f"判定士{inspector_id}",
        )

        # 進行方向が少し分かるように、各線分の途中に小さな矢印を描きます。
        for from_node, to_node in zip(route[:-1], route[1:]):
            from_location = locations[from_node]
            to_location = locations[to_node]
            dx = to_location.x - from_location.x
            dy = to_location.y - from_location.y

            plt.arrow(
                from_location.x,
                from_location.y,
                dx * 0.75,
                dy * 0.75,
                color=color,
                length_includes_head=True,
                head_width=1.5,
                alpha=0.45,
            )

    plt.title("応急危険度判定: 複数判定士による巡回ルート最適化")
    plt.xlabel("X座標")
    plt.ylabel("Y座標")
    plt.xlim(-5, MAP_SIZE + 5)
    plt.ylim(-5, MAP_SIZE + 5)
    plt.grid(True, linestyle="--", alpha=0.4)
    plt.legend()
    plt.tight_layout()
    plt.show()


def main() -> None:
    """プログラム全体の流れです。"""

    timings: dict[str, float] = {}
    total_start = time.perf_counter()

    start = time.perf_counter()
    locations = generate_locations()
    timings["generate_locations"] = time.perf_counter() - start

    start = time.perf_counter()
    distance_matrix = create_distance_matrix(locations)
    timings["create_distance_matrix"] = time.perf_counter() - start

    start = time.perf_counter()
    result = solve_mtsp(distance_matrix)
    timings["solve_mtsp"] = time.perf_counter() - start

    if result is None:
        print("解が見つかりませんでした。制約や探索時間を見直してください。")
        return

    routing, manager, solution = result
    start = time.perf_counter()
    routes = extract_routes(routing, manager, solution)
    timings["extract_routes"] = time.perf_counter() - start
    timings["total_before_plot"] = time.perf_counter() - total_start

    print_routes(routes)
    print_timing_report(timings)
    plot_routes(locations, routes)


if __name__ == "__main__":
    main()
