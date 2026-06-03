# Python OR-Tools mTSP: 応急危険度判定シミュレーション

OR-Toolsを使って、応急危険度判定を題材にした Multiple Traveling Salesman Problem, mTSP を解くハンズオン用コードです。

- 0番地点を災害対策本部として扱います。
- 1〜20番地点を判定対象建物としてランダム生成します。
- 3人の判定士が本部から出発し、本部へ戻ります。
- 全ての建物を必ず1回訪問します。
- 最長ルートを短くする設定により、担当の偏りを抑えます。
- matplotlibで経路を可視化します。
- 実行時間も計測します。

## セットアップ

Python 3.10以上を推奨します。

```powershell
pip install ortools matplotlib
```

Windowsで複数のPythonが入っている場合は、次の実行方法も使えます。

```powershell
py -m pip install ortools matplotlib
```

## 実行

```powershell
python mtsp_emergency_assessment.py
```

または:

```powershell
py mtsp_emergency_assessment.py
```

## 実験設定の変更

`mtsp_emergency_assessment.py` の冒頭付近にある定数を変更します。

```python
NUM_BUILDINGS = 20
NUM_INSPECTORS = 3
SOLVER_TIME_LIMIT_SECONDS = 10
```

30分探索したい場合は、次のように変更します。

```python
SOLVER_TIME_LIMIT_SECONDS = 1800
```

## 発展案

- Google Maps Platformなどを使い、直線距離ではなく道路距離を使う
- 建物ごとに危険度、調査時間、優先度を設定する
- 判定士ごとの移動速度や経験値を設定する
- 道路閉塞、担当区域、帰着時刻制約を加える
- GISデータと連携して実市街地に近いシミュレーションにする
