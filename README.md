# 応急危険度判定 mTSP シミュレーター

Python と OR-Tools を使って、複数の判定士が複数の建物を分担して巡回する
mTSP（Multiple Traveling Salesman Problem）を解くハンズオン用コードです。

## できること

- 0番地点を災害対策本部として固定
- 1番以降の地点を判定対象建物としてランダム生成
- 複数の判定士が本部から出発し、本部へ戻るルートを計算
- 全ての建物を必ず1回訪問
- 最長ルートを短くすることで担当の偏りを抑制
- GUIでパラメータを変更
- matplotlibで経路を可視化

## インストール

Windows の PowerShell またはコマンドプロンプトで実行します。

```powershell
py -m pip install -r requirements.txt
```

`py` が使えない場合は、次を試してください。

```powershell
python -m pip install -r requirements.txt
```

## 実行方法

```powershell
py mtsp_emergency_inspection.py
```

または

```powershell
python mtsp_emergency_inspection.py
```

## GUIで変更できるパラメータ

- 乱数シード
- 判定対象建物数
- 判定士数
- 探索時間
- 偏り抑制係数
- 経路図を表示するかどうか

## 研究へ発展させるための改造ポイント

- 実道路ネットワークを使った距離行列に変更する
- 道路閉塞や橋梁被害を通行不可・高コストとして反映する
- 建物ごとの危険度、判定所要時間、優先度を追加する
- 判定士ごとの経験差、移動速度、担当可能エリアを追加する
- GISデータや避難所・公共施設データと接続する
- 時間窓制約を入れて、一定時刻までに優先建物を回るモデルにする

