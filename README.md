# 応急危険度判定 mTSP シミュレーター

Python と OR-Tools を使って、複数の判定士が複数の建物を分担して巡回する
mTSP（Multiple Traveling Salesman Problem）を解くハンズオン用コードです。

## できること

- 0番地点を災害対策本部として固定
- 1番以降の地点を判定対象建物としてランダム生成
- 複数の判定士が本部から出発し、本部へ戻るルートを計算
- 全ての建物を必ず1回訪問
- 最長ルートを短くすることで担当の偏りを抑制
- matplotlibで経路を可視化
- 実行時間を計測

## ファイル

- `mtsp_emergency_assessment.py`
  - 1ファイルで実行できるCLI版です。
  - 地点生成、距離行列作成、OR-Tools最適化、結果抽出の実行時間を表示します。
- `mtsp_emergency_inspection.py`
  - GUIでパラメータを変更できる版です。
- `benchmark_mtsp.py`
  - 複数条件をまとめて実行し、性能指標をCSV保存するベンチマーク版です。
- `benchmark_gui.py`
  - ベンチマーク条件を画面上で指定できるGUI版です。
- `requirements.txt`
  - 必要なPythonパッケージ一覧です。

## インストール

Windows の PowerShell またはコマンドプロンプトで実行します。

```powershell
py -m pip install -r requirements.txt
```

`py` が使えない場合は、次を試してください。

```powershell
python -m pip install -r requirements.txt
```

## CLI版の実行

```powershell
py mtsp_emergency_assessment.py
```

または:

```powershell
python mtsp_emergency_assessment.py
```

## GUI版の実行

```powershell
py mtsp_emergency_inspection.py
```

または:

```powershell
python mtsp_emergency_inspection.py
```

## ベンチマーク版の実行

描画なしで複数条件をまとめて実行し、CSVに保存します。

```powershell
py benchmark_mtsp.py
```

条件を指定する例です。

```powershell
py benchmark_mtsp.py --buildings 200 500 1000 --inspectors 3 5 10 --time-limits 10 30 60 --seeds 42 43 44 --output benchmark_results.csv
```

CSVには、次のような指標が出力されます。

- 解が見つかったか
- 距離行列作成時間
- OR-Tools最適化時間
- 探索以外の処理時間
- 合計移動距離
- 最長ルート距離
- 平均ルート距離
- 偏り率（最長ルート距離 / 平均ルート距離）
- 判定士ごとの担当建物数
- Python側のピークメモリ使用量（`--trace-memory` 指定時）

`total_time_seconds` は、指定した探索時間を含む全体の壁時計時間です。
そのため、探索時間を10秒、30秒、60秒と変える実験では、
`total_time_seconds` をそのまま性能比較の主指標にしないでください。

性能の確認では、次の列を分けて見ます。

- `setup_time_seconds`: 地点生成 + 距離行列作成
- `non_solver_time_seconds`: 地点生成 + 距離行列作成 + 結果抽出
- `solve_time_seconds`: OR-Toolsに使わせた探索時間
- `solve_overrun_seconds`: 実際の探索時間 - 探索時間上限
- `solve_time_ratio`: 実際の探索時間 / 探索時間上限

モデル性能を見るときは、同じ建物数・判定士数・乱数シードで
探索時間を伸ばしたときに、`max_distance` や `imbalance_ratio` が
どの程度改善するかを比較します。

メモリ計測も行う場合は次のように実行します。大規模ケースでは計測自体が遅くなることがあります。

```powershell
py benchmark_mtsp.py --buildings 500 1000 --inspectors 5 10 --time-limits 10 --trace-memory
```

## ベンチマークGUI版の実行

ベンチマーク条件を画面上で入力して実行できます。

```powershell
py benchmark_gui.py
```

入力欄には、複数値をスペース、カンマ、改行区切りで入力できます。

```text
建物数: 200 500 1000
判定士数: 3 5 10
探索時間: 10 30 60
乱数シード: 42 43 44
```

実行中は進捗バーとログが更新され、各ケースの結果がCSVに保存されます。

## 実験設定の変更

CLI版では、`mtsp_emergency_assessment.py` の冒頭付近にある定数を変更します。

```python
NUM_BUILDINGS = 20
NUM_INSPECTORS = 3
SOLVER_TIME_LIMIT_SECONDS = 10
```

30分探索したい場合は、次のように変更します。

```python
SOLVER_TIME_LIMIT_SECONDS = 1800
```

GUI版では、画面上で次のパラメータを変更できます。

- 乱数シード
- 判定対象建物数（最大2000）
- 判定士数
- 探索時間
- 偏り抑制係数
- 経路図を表示するかどうか

地点数を大きくする場合は、matplotlibの描画や地点番号表示が重くなるため、
まずは「経路図を表示するかどうか」をOFFにして計算時間を確認することをおすすめします。

## 研究へ発展させるための改造ポイント

- 実道路ネットワークを使った距離行列に変更する
- Google Maps Platformなどを使い、直線距離ではなく道路距離を使う
- 道路閉塞や橋梁被害を通行不可・高コストとして反映する
- 建物ごとの危険度、判定所要時間、優先度を追加する
- 判定士ごとの経験差、移動速度、担当可能エリアを追加する
- GISデータや避難所・公共施設データと接続する
- 時間窓制約を入れて、一定時刻までに優先建物を回るモデルにする
