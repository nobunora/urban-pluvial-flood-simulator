# 国土地理院の1m級DEM（DEM1A）を入手する

## 公式入口

- 基盤地図情報サイト: https://www.gsi.go.jp/kiban/
- 基盤地図情報ダウンロードサービス: https://service.gsi.go.jp/kiban/
- 高精度標高データ: https://www.gsi.go.jp/gazochosa/gazochosa41019.html

## DEM1Aのダウンロード

2026年8月時点の基本的な手順です。

1. 基盤地図情報ダウンロードサービスを開く
1. 無料の利用者登録を行い、ログインする
1. `数値標高モデル`を選択する
1. 通常は`最新データ`を選ぶ
1. `1mメッシュ` → `1A（航空レーザ測量）`を選ぶ
1. 地図上で必要な範囲を選択する
1. 検索結果をダウンロードリストへ追加する
1. ZIPを取得する

数値標高モデルの配布形式はJPGIS（GML）です。

1m DEMのデータ本体は3次メッシュ単位で提供されます。ダウンロードZIPの中に複数のXML/GMLが含まれることがあります。

## 重要：1mは水平格子間隔

DEM1Aは航空レーザ測量を基にした約1m格子です。

国土地理院の標高タイル説明では、DEM1Aの標高精度は標準偏差0.3m以内とされています。

つまり、`1mメッシュ`は「1mごとに標高値がある」という意味であって、「高さが1mあるいは数cmの精度で必ず正しい」という意味ではありません。

洪水解析では数cm〜数十cmの差が流路を変える場合があるため、この点は重要です。

公式説明:
https://maps.gsi.go.jp/development/hyokochi.html

## 提供範囲

DEM1Aは順次提供範囲が拡大されていますが、必要な場所に必ず存在するとは限りません。

最新範囲は次のページで確認してください。

https://www.gsi.go.jp/gazochosa/gazochosa41019.html

DEM1Aがない場合は、DEM5Aなどを候補にします。

## 建物・道路を取得する

同じ基盤地図情報ダウンロードサービスの`基本項目`から、都市水理モデルに使える地物も取得できます。

今回の参考実装で利用する主なものは次です。

- 建築物の外周線
- 道路縁

公式説明:
https://www.gsi.go.jp/kiban/towa.html

## DEM1A ZIPを解析用NPZへ変換する

```bash
python scripts/gsi_dem1a_to_npz.py \
  --zip DEM1A_A.zip \
  --center-lat <LATITUDE> \
  --center-lon <LONGITUDE> \
  --half-size-m 1000 \
  --grid-m 1 \
  --out dem_1m.npz
```

ダウンロードファイル境界をまたぐ場合は`--zip`を繰り返します。

```bash
python scripts/gsi_dem1a_to_npz.py \
  --zip DEM1A_A.zip \
  --zip DEM1A_B.zip \
  --zip DEM1A_C.zip \
  --center-lat <LATITUDE> \
  --center-lon <LONGITUDE> \
  --half-size-m 1000 \
  --grid-m 1 \
  --out dem_1m.npz
```

引数で先に書いたZIPほど優先度が高く、完全重複地点では先頭ソースを採用します。

デフォルトでは、異なるソース境界の人工段差を20m幅のcosine taperで補正します。無効化する場合は次を指定します。

```bash
--blend-width-m 0
```

## 基本項目ZIPを建物・道路ベクトルへ変換する

```bash
python scripts/gsi_basic_to_vectors.py \
  --zip BASIC_A.zip \
  --zip BASIC_B.zip \
  --center-lat <LATITUDE> \
  --center-lon <LONGITUDE> \
  --half-size-m 1000 \
  --out-dir vectors
```

出力:

```text
vectors/buildings.npz
vectors/basemap_vectors.npz
```

## 水理入力を作る

```bash
python scripts/prepare_inputs.py \
  --dem dem_1m.npz \
  --buildings vectors/buildings.npz \
  --vectors vectors/basemap_vectors.npz \
  --out hydraulic_inputs
```

## 国土地理院GMLで注意する点

国土地理院FAQでは、数値標高モデルの構成点は北西端から開始し、西→東へ進んだ後、南方向へ行を進める順序とされています。

また先頭の無効値が連続する場合、`gml:startPoint`によって省略される場合があります。

参考スクリプト`gsi_dem1a_to_npz.py`ではこれを考慮して配列を復元します。

公式FAQ:
https://service.gsi.go.jp/kiban/app/faq/

## タイル境界について

国土地理院は、元となる標高モデルが変わる境界などで標高値が不連続になる場合があると説明しています。

公式説明:
https://maps.gsi.go.jp/development/hyokochi.html

洪水解析では小さな段差でも人工的な堤防として働く可能性があるため、境界確認を推奨します。
