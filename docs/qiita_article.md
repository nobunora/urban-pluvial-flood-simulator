# 1m DEM × Local-Inertial法で都市洪水を2次元シミュレーションする

## この記事でやること

国土地理院が公開している**1m級の数値標高モデル（DEM1A）**と基盤地図情報を使い、都市部に強い雨が降ったときに、水がどこへ流れ、どこに溜まるかを2次元で計算します。

今回のモデルは、単純に「地面の低い方向へ水を流す」だけではありません。

水が流れる方向を決めるときは、地面の高さではなく、

```text
水面の高さ = 地面の高さ + その場所に溜まっている水深
```

を使います。

そのため、下流側にすでに水が溜まっていれば流れにくくなり、水位が逆転すれば逆流もできます。

都市を再現するために、さらに次の情報も入れます。

- 建物は水が通り抜けない障害物として扱う
- 道路は周囲より水が流れやすい粗度を与える
- 屋根に降った雨は消さず、建物外周へ再配分する
- 計算が不安定にならないよう時間刻みを自動調整する
- セルに存在する量以上の水を流出させない

計算の中心には、浅水方程式を簡略化した**Local-Inertial Approximation**を使います。

今回の参考実装では、たとえば`2001 × 2001`の1m格子なら約400万セルを計算します。

## まずイメージだけ掴む

洪水計算をかなり乱暴に説明すると、各セルで次の処理を繰り返しています。

```text
雨が降る
  ↓
各セルの水深が増える
  ↓
地面 + 水深 から水面の高さを計算
  ↓
隣のセルとの水面差を求める
  ↓
Local-Inertial式でセル間流量を計算
  ↓
建物なら流量を0にする
  ↓
道路なら摩擦を小さくする
  ↓
流入量 - 流出量 から新しい水深を計算
  ↓
次の時刻へ
```

ここで大事なのは、**地形は固定でも、水面は時間とともに変化する**ことです。

たとえば地面だけを見ると下り坂でも、下流側に大量の水が溜まっていれば、水面はほぼ水平かもしれません。

その場合、水はほとんど流れません。

逆に下流側の水面の方が高ければ、地面の勾配とは逆方向へ水が戻ることもあります。

これが単純なD8流向計算と水理モデルの大きな違いです。

## 全体フロー

今回の処理全体は次の構成です。

```text
国土地理院 DEM1A
        ↓
JPGIS(GML)を読み込む
        ↓
ローカル1m直交格子へ再サンプリング
        ↓
DEM境界の段差を補正
        ↓
基盤地図情報から建物・道路をRasterize
        ↓
Manning粗度マップを作る
        ↓
屋根降雨の再配分係数を作る
        ↓
Rain-on-Grid
        ↓
Local-Inertial 2D solver
        ↓
Adaptive CFL
        ↓
Wet/Dry + Donor limiter
        ↓
水深・最大水深・流量を保存
        ↓
レインボーカラーで可視化
```

## 1m級DEMを国土地理院から入手する

2026年8月時点では、国土地理院の**基盤地図情報ダウンロードサービス**からDEM1Aを取得できます。

[基盤地図情報ダウンロードサービス](https://service.gsi.go.jp/kiban/)

1mメッシュは航空レーザ測量を基にした`1A`として提供されています。

### ダウンロード手順

1. [基盤地図情報ダウンロードサービス](https://service.gsi.go.jp/kiban/)を開く
1. 利用者登録してログインする
1. **数値標高モデル**を選択する
1. 作成年月は通常**最新データ**を選択する
1. 対象メッシュで**1mメッシュ → 1A（航空レーザ測量）**を選ぶ
1. 地図上で必要範囲を選択する
1. 検索結果をダウンロードリストへ追加する
1. ZIPをダウンロードする

国土地理院の公式ヘルプによると、数値標高モデルは1m、5m、10mがあり、ダウンロード形式は**JPGIS（GML）形式**です。

[基盤地図情報ダウンロードサービス ヘルプ](https://service.gsi.go.jp/kiban/app/help/)

1m DEMのデータ本体は**3次メッシュ単位**で提供されます。

[基盤地図情報に関するFAQ](https://www.gsi.go.jp/kiban/faq.html)

ZIPを展開すると、次のようなGML/XMLが入っています。

```text
FG-GML-xxxx-xx-xx-DEM1A-yyyyMMdd.xml
```

### 「1mメッシュ」と「標高精度0.3m」は別の話

ここはかなり重要です。

DEM1Aは約1m間隔の格子ですが、これは**水平格子間隔**の話です。

国土地理院が公開している標高タイルの説明では、DEM1Aは航空レーザ測量による約1m四方の格子で、標高精度は**標準偏差0.3m以内**とされています。

[標高タイルの作成方法と地理院地図で表示される標高値について](https://maps.gsi.go.jp/development/hyokochi.html)

つまり、

```text
1mメッシュ
```

だからといって、

```text
標高が1cm単位で正確
```

という意味ではありません。

1m洪水解析では数cm～数十cmの地形差が結果に強く影響するため、この違いは必ず意識する必要があります。

### 1m DEMは全国一律ではない

1m DEMの提供範囲は順次拡大されています。

必要な場所にDEM1Aが存在するかは、国土地理院の高精度標高データページやダウンロード画面で確認します。

[高精度標高データ](https://www.gsi.go.jp/gazochosa/gazochosa41019.html)

DEM1Aが存在しない場所では、DEM5Aなどへ落とす必要があります。

### 建物と道路も同じサービスから入手できる

基盤地図情報の**基本項目**には、道路縁や建築物の外周線なども含まれています。

[基盤地図情報とは](https://www.gsi.go.jp/kiban/towa.html)

今回のモデルでは、これらを使って、

- 建物 → no-flow boundary
- 道路 → Manning粗度を変更

という水理条件へ変換します。

## 公開している参考ソース

GitHub用の参考実装は次の構成を想定しています。

```text
local-inertial-flood-reference/
├─ README.md
├─ CMakeLists.txt
├─ requirements.txt
├─ src/
│  └─ solver.cpp
├─ scripts/
│  ├─ gsi_dem1a_to_npz.py
│  ├─ prepare_inputs.py
│  └─ plot_results.py
└─ docs/
   ├─ qiita_article.md
   ├─ data_download.md
   └─ references.md
```

DEM1AのZIPから解析用DEMを作る場合は、例えば次のように実行します。

```bash
python scripts/gsi_dem1a_to_npz.py \
  --zip FG-GML-XXXXXX-DEM1A-YYYYMMDD.zip \
  --center-lat <LATITUDE> \
  --center-lon <LONGITUDE> \
  --half-size-m 1000 \
  --grid-m 1 \
  --out dem_1m.npz
```

ダウンロードファイル境界をまたぐ場合は`--zip`を複数指定します。

```bash
python scripts/gsi_dem1a_to_npz.py \
  --zip west.zip \
  --zip east.zip \
  --zip south-west.zip \
  --zip south-east.zip \
  --center-lat <LATITUDE> \
  --center-lon <LONGITUDE> \
  --half-size-m 1000 \
  --grid-m 1 \
  --out dem_1m.npz
```

---

> **概要だけ知りたかった人は、ここまでで十分です。**
>
> 要するに「1m DEMの上に雨を直接降らせ、地面ではなく水面の高さの差から流量を計算し、建物や道路も条件として入れる」というシミュレーションです。
>
> **ここから先は、数値計算・離散化・安定化処理まで知りたい人向けです。**

---

## ここから技術詳細：状態量をどこに持つか

最初に決めるのが配列配置です。

水深`h`と地盤標高`z`はセル中心に持たせます。

x方向流量`qx`とy方向流量`qy`はセル境界に持たせます。

```text
              qy[i,j]
                 ↑
        +----------------+
        |                |
 qx ←   |    h[i,j]      |   → qx
        |                |
        +----------------+
                 ↓
                qy
```

`N × N`セルなら、配列サイズは概ね次のようになります。

```text
h, z     : N × N
qx       : N × (N - 1)
qy       : (N - 1) × N
```

この配置にすると、セル内の水量とセル面を横切る流量を分離できます。

連続式の離散化も単純になります。

## 水面標高を計算する

地盤標高だけではなく、水面標高`η`を使います。

```math
\eta = z + h
```

ここで、

- `z`：地盤標高
- `h`：水深
- `η`：水面標高

です。

隣接セル`i`と`i+1`の水面勾配は、

```math
S = \frac{\eta_{i+1}-\eta_i}{\Delta x}
```

として求めます。

この水面勾配が、Local-Inertial式の駆動力になります。

## Local-Inertial Approximation

Full Shallow Water Equationsには、

- 局所慣性
- 移流慣性
- 圧力勾配
- 底面摩擦

などが含まれます。

Local-Inertial Approximationでは主に**移流慣性項を省略**し、局所慣性は残します。

x方向の概念式は次の形です。

```math
\frac{\partial q}{\partial t}
+
gh\frac{\partial \eta}{\partial x}
+
gn^2\frac{q|q|}{h^{7/3}}
=0
```

ここで、

- `q`：単位幅流量 `[m²/s]`
- `g`：重力加速度
- `h`：水深
- `n`：Manning粗度

です。

Bates et al. (2010)は、このLocal-Inertial formulationを2次元洪水計算向けの計算効率の良い浅水方程式近似として提示しています。

[論文：A simple inertial formulation of the shallow water equations for efficient two-dimensional flood inundation modelling](https://doi.org/10.1016/j.jhydrol.2010.03.027)

## Face water depthをどう決めるか

隣接2セルの地盤高さが異なる場合、単純に平均水深を使うと不自然な流量が発生します。

そこでセル面で有効な水深`h_f`を、

```math
h_f = \max(\eta_a, \eta_b) - \max(z_a, z_b)
```

として求めます。

`h_f <= 0`なら、そのセル面を越える水柱が存在しないので流量を0にします。

この処理により、小さな地形段差を水面が超えるまでは流れず、水位が段差を超えたら流れ始める挙動になります。

## de Almeida型の流量安定化

1m格子では、隣接セル間の流量が1ステップごとに反転する数値振動が発生しやすくなります。

そこでde Almeida et al. (2012)の考え方を参考に、現在faceの流量と隣接faceの流量を重み付けします。

```math
\bar q_i
=
\theta q_i
+
\frac{1-\theta}{2}
\left(q_{i-1}+q_{i+1}\right)
```

今回の参考値は、

```text
θ = 0.8
```

です。

C++では概ね次の部分です。

```cpp:solver.cpp
const float neighbour_weight = 0.5f * (1.f - theta);

const float q_left  = (j > 0) ? qx[e - 1] : 0.f;
const float q_right = (j < N - 2) ? qx[e + 1] : 0.f;

const float qbar =
    theta * qx[e]
    + neighbour_weight * (q_left + q_right);
```

参考：

[Improving the stability of a simple formulation of the shallow water equations for 2-D flood modeling](https://doi.org/10.1029/2011WR011570)

## Manning摩擦を半陰的に扱う

face dischargeは参考実装では次の形で更新しています。

```math
q^{n+1}
=
\frac{
\bar q
-
gh_f\Delta tS
}{
1
+
g\Delta t n_f^2
\frac{|\bar q|}{h_f^{7/3}}
}
```

摩擦項を分母側へ入れることで、摩擦を完全explicitに扱うより安定化しやすくなります。

C++では次のようになります。

```cpp:solver.cpp
const float slope = (eta_b - eta_a) / dx;
const float nf = 0.5f * (manning[a] + manning[b]);
const float h73 = hf * hf * std::cbrt(hf);

const float denominator =
    1.f
    + g * dt * nf * nf
    * std::fabs(qbar)
    / std::max(h73, 1e-12f);

const float qn =
    (qbar - g * hf * dt * slope)
    / denominator;
```

ここは計算負荷的にも重要です。

`h^(7/3)`を全セル面で毎ステップ計算するため、400万セル級ではこのようなべき乗計算も無視できなくなります。

## 連続式で水深を更新する

流量を求めたら、セル内水量を連続式で更新します。

```math
\frac{\partial h}{\partial t}
+
\frac{\partial q_x}{\partial x}
+
\frac{\partial q_y}{\partial y}
=R
```

離散化すると、

```math
h_{i,j}^{n+1}
=
h_{i,j}^{n}
+
\Delta t
\left[
R
-
\frac{q_E-q_W}{\Delta x}
-
\frac{q_N-q_S}{\Delta y}
\right]
```

となります。

つまり、

```text
次の水深
=
現在の水深
+ 降雨
+ 流入
- 流出
```

です。

## Rain-on-Grid

雨は計算領域全体へ直接与えます。

降雨強度`P [mm/h]`は、

```math
R = \frac{P/1000}{3600}
```

で`m/s`へ変換します。

たとえば`115 mm/h`なら、

```math
R
\approx
3.19 \times 10^{-5}\;m/s
```

です。

1m × 1mセルなら、1秒当たり同じ値の`m³`が1セルへ加わります。

## Adaptive CFL

1m格子では固定時間刻みがかなり危険です。

水深が増えると重力波速度`√(gh)`が大きくなるため、同じ`Δt`ではCFL条件を破りやすくなります。

そこで全セルの最大水深から時間刻みを毎ステップ更新します。

```math
\Delta t
\le
\alpha
\frac{\Delta x}{\sqrt{gh_{max}}}
```

参考実装では、

```text
α = 0.7
dt_max = 2.0 s
```

です。

```cpp:solver.cpp
float dt = dt_max;

if (h_global_max > hmin) {
    dt = cfl_alpha * dx / std::sqrt(g * h_global_max);
    dt = std::min(dt, dt_max);
    dt = std::max(dt, dt_min);
}
```

この方法はかなり保守的です。

毎ステップ全領域の最大値を取るので、1か所だけ深い場所があっても領域全体の時間刻みが小さくなります。

その代わり、実装が明快で検証しやすいという利点があります。

## Wet/Dry処理

水深がほぼ0のセルまで通常の式へ入れると、Manning摩擦の`h^(-7/3)`が非常に大きくなります。

そこで、

```text
h <= h_min
```

を乾燥セルとして扱います。

ただし、単純に乾燥セルからの流量をすべて0にすると、水が段差を越えて新しいセルへ浸水できません。

そのため、参考実装では、

- donor側にほぼ水がない
- かつ水面が隣接セル地盤を越えていない

場合だけ流量を止めます。

```cpp:solver.cpp
if (qn > 0.f && h[a] <= hmin && eta_a <= z[b] + hmin)
    qn = 0.f;

if (qn < 0.f && h[b] <= hmin && eta_b <= z[a] + hmin)
    qn = 0.f;
```

この条件があることで、地形段差より水面が高くなれば乾燥セル側へ浸水できます。

## 負水深を防ぐDonor limiter

数値計算では、あるセルに存在する水量より多くの水を1ステップで流出させようとすることがあります。

そのまま計算すると、

```text
h < 0
```

になります。

更新後に単純に、

```python
h = max(h, 0)
```

とすると、負になった分の質量が勝手に消えるため、質量保存が崩れます。

そこで**流量そのものを縮小**します。

セルから出ようとしている総流量を`Qout`とすると、1ステップで必要な水深は、

```math
h_{req}
=
\frac{Q_{out}\Delta t}{\Delta x}
```

です。

利用可能な水深より大きければ、

```math
scale
=
\frac{h_{available}}{h_{req}}
```

を全流出faceへ掛けます。

```cpp:solver.cpp
const float available_depth =
    h[a] + rain * rain_weight[a] * dt;

const float requested_depth =
    outflow * dt / dx;

const float scale =
    requested_depth > available_depth
    ? available_depth / requested_depth
    : 1.f;
```

この処理は1m格子のWet/Dry frontでかなり重要です。

## 建物をno-flow boundaryにする

DEMだけで計算すると、水は建物を普通に横切ります。

そこで建物ポリゴンを1mグリッドへRasterizeして、建物セルを作ります。

建物セルと地表セルの間では、

```math
q = 0
```

にします。

```cpp:solver.cpp
if (building[a] || building[b]) {
    qx_new[e] = 0.f;
    continue;
}
```

これによって、道路や建物間の隙間へ流れが集中します。

都市洪水ではこの違いが非常に大きいです。

## 屋根に降った雨を質量保存する

建物をno-flowセルにしただけでは、建物セルへ降った雨が消えてしまいます。

そこで参考実装では、建物を連結成分ごとに分け、屋根面積分の雨を建物外周の地表セルへ再配分します。

処理は次のようになっています。

1. 建物マスクを連結成分に分割する
1. 各建物のセル数を数える
1. 建物と地表の4近傍境界edge数を数える
1. 屋根セル数を境界edge数で割る
1. その係数を建物外周セルの`rain_weight`へ加える

このとき、

```text
sum(rain_weight) ≒ total grid cell count
```

になることを確認します。

つまり屋根を遮水したことで**降雨質量が消えない**ようにしています。

```python:prepare_inputs.py
print(
    "rain-weight mass check:",
    rain_weight.sum(),
    "/",
    z.size,
)
```

実際の雨樋位置を知っているなら、外周へ均等分配するのではなく雨樋セルへ集中させた方が現実的です。

## 道路だけManning粗度を下げる

道路は周囲の宅地より水が流れやすいため、粗度マップを別に持ちます。

参考値は、

```text
一般地表 : n = 0.030
道路     : n = 0.020
```

です。

```python:prepare_inputs.py
manning = np.full(z.shape, 0.030, dtype=np.float32)
manning[road_mask] = 0.020
```

参考実装では基盤地図情報の道路縁をそのまま1ピクセルだけRasterizeせず、一定幅bufferして簡易的な道路領域へ変換しています。

これは道路幅データが別にない場合の簡易処理です。

## DEM1AのGMLをどう読んでいるか

国土地理院DEM1AのGMLでは、主に次の情報を読みます。

```xml
<gml:lowerCorner>...</gml:lowerCorner>
<gml:upperCorner>...</gml:upperCorner>
<gml:high>...</gml:high>
<gml:tupleList>
...
</gml:tupleList>
<gml:startPoint>...</gml:startPoint>
```

公式FAQによると、数値標高モデルの構成点は、

1. 北西端から開始
1. x方向の正方向、つまり西→東へ進む
1. 東端へ達すると南側の行へ進む
1. 南東端へ到達

という順序です。

[基盤地図情報ダウンロードサービス FAQ](https://service.gsi.go.jp/kiban/app/faq/)

`startPoint`は、先頭にデータなしセルが連続する場合に、その部分を省略するために使われます。

参考スクリプトでは、

```python:gsi_dem1a_to_npz.py
start_flat = sy * nx + sx

flat = np.full(nx * ny, np.nan, dtype=np.float32)
flat[start_flat:start_flat + len(values)] = values

arr = flat.reshape(ny, nx)
```

として復元しています。

## 緯度経度DEMを1m直交格子へ変換する

DEM1Aは緯度経度上の格子です。

水理計算では、

```text
Δx = 1m
Δy = 1m
```

の直交格子の方が扱いやすいため、計算中心を原点とするローカルAzimuthal Equidistant座標系へ変換します。

```python:gsi_dem1a_to_npz.py
crs_local = CRS.from_proj4(
    f"+proj=aeqd "
    f"+lat_0={center_lat} "
    f"+lon_0={center_lon} "
    "+ellps=GRS80 +units=m +no_defs"
)
```

出力1m格子の各セル中心を逆変換して緯度経度へ戻し、元DEMを双線形補間します。

```python:gsi_dem1a_to_npz.py
row = (lat_max - lat) / (lat_max - lat_min) * (ny - 1)
col = (lon - lon_min) / (lon_max - lon_min) * (nx - 1)

sample = map_coordinates(
    tile,
    [row, col],
    order=1,
    mode="nearest",
    prefilter=False,
)
```

## DEMタイル境界の段差をどう扱うか

高解像度DEMでは、異なる取得時期や原典データの境界に人工的な標高差が見える場合があります。

国土地理院も、元となる標高モデルが変わる境界では標高値が不連続になる場合があると説明しています。

[標高タイルの作成方法と地理院地図で表示される標高値について](https://maps.gsi.go.jp/development/hyokochi.html)

洪水解析でこの段差を残すと、数cm～数十cmの人工堤防として作用する可能性があります。

そこで参考実装では、優先する基準DEMを決め、隣接DEM側だけを一定幅で補正します。

境界の基準側2セルから、隣接側の本来の高さを線形外挿します。

```math
z_{target}
=
2z_{edge}-z_{inner}
```

隣接タイル境界との差を、

```math
\Delta z
=
z_{target}-z_{neighbor}
```

とし、境界から内部へ向かってcosine taperで補正量を減らします。

```math
w(d)
=
\frac{1}{2}
\left[
1+
\cos\left(\pi\frac{d}{W}\right)
\right]
```

最終補正は、

```math
z' = z + w(d)\Delta z
```

です。

`W = 20m`なら、境界では補正を100%適用し、20m内側で0になります。

重要なのは、**DEM全体を平滑化しない**ことです。

水理解析では本物の微地形まで消すと意味がないため、補正はデータソース境界付近だけに限定します。

## 開放境界

計算領域の外周を壁にすると、雨水が領域外へ出られません。

参考実装では最外周1セルをsinkとして水深0へ戻す簡易open boundaryを採用しています。

```cpp:solver.cpp
if (
    i == 0
    || j == 0
    || i == N - 1
    || j == N - 1
) {
    hn = 0.f;
}
```

これは簡単ですが、境界条件としてはかなり強い仮定です。

実務的な計算では、対象地点より十分広い範囲を取るか、河川水位などの境界水位を与える必要があります。

## 最大水深は別に保存する

最終時刻の水深だけでは、洪水リスクを過小評価する可能性があります。

たとえば、

```text
30分 : 1.2m
60分 : 0.4m
```

なら、終了時の0.4mだけ保存すると最大浸水を見逃します。

そこで毎ステップ、

```cpp:solver.cpp
if (hn > hmax[a])
    hmax[a] = hn;
```

として最大水深を別配列へ保存します。

## 1時間計算でも時間ステップ数はかなり増える

1m格子ではAdaptive CFLによって時間刻みがかなり小さくなる場合があります。

約400万セルの計算で、強い降雨を1時間与えると、条件によっては数万ステップになることがあります。

この規模になると、数式以上にメモリアクセスが重要になります。

避けたい実装は、

- Pythonのセル単位for-loop
- 毎ステップの巨大配列コピー
- 必要のない`float64`
- 毎ステップのファイル保存
- temporary arrayの大量生成

です。

参考実装では水理solverをC++にし、OpenMPでface更新とセル更新を並列化しています。

```bash
OMP_NUM_THREADS=8 ./solver \
  2001 \
  1.0 \
  3600 \
  115 \
  hydraulic_inputs \
  result
```

## コンパイル

直接GCCを使うなら、

```bash
g++ -O3 -march=native -fopenmp -std=c++17 \
  src/solver.cpp \
  -o solver
```

CMakeを使うなら、

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
```

でビルドできます。

## 出力

参考solverはI/Oを軽くするため、raw float32 binaryで出力します。

```text
result_h.bin      最終水深
result_hmax.bin   計算中最大水深
result_qx.bin     最終x方向face流量
result_qy.bin     最終y方向face流量
```

可視化はPython側で行います。

```bash
python scripts/plot_results.py \
  --metadata hydraulic_inputs/metadata.npz \
  --prefix result \
  --out max_depth_rainbow.png
```

カラーマップには`turbo`を使っています。

## 最低限確認すべき数値検証

自作水理solverでは、画像がそれっぽく見えるだけでは不十分です。

最低限、次を確認します。

### 質量保存

```text
総降雨入力
-
領域外流出
-
最終貯留量
```

が十分小さいか確認します。

### 時間刻み依存性

CFL係数や`dt_max`を小さくして、結果が大幅に変化しないか比較します。

### 負水深

`h < 0`が発生していないことを確認します。

### DEM境界

補正前後でタイル境界が人工的な堤防や溝になっていないか確認します。

### 屋根降雨の質量

```text
sum(rain_weight) ≒ 全セル数
```

になっているか確認します。

### 解法比較

可能であれば一部領域をHEC-RAS 2D、LISFLOOD-FP、Full SWE solverなどと比較します。

## Local-Inertial法が向く流れ、向かない流れ

Local-Inertial法は計算量と物理性のバランスが良い一方、万能ではありません。

de Almeida & Bates (2013)では、Local-Inertial approximationの適用性がFull Dynamic shallow-water modelと比較されています。

[Applicability of the local inertial approximation of the shallow water equations to flood modeling](https://doi.org/10.1002/wrcr.20366)

都市内水のような、

- 低Froude数
- subcritical flow
- 緩勾配
- 摩擦支配

では有力な選択肢です。

一方で、

- ダム決壊
- 強い段波
- hydraulic jump
- 高速ジェット
- supercritical flow

まで正確に扱うなら、Full Shallow Water Equationsを検討した方がよいです。

## このモデルでまだ入っていないもの

今回の参考実装は地表2Dモデルです。

実都市ではさらに、

- 雨水桝
- 側溝
- 下水管路
- 河川水位
- 地中浸透
- 縁石
- 塀
- 建物入口からの浸水

などが効きます。

特に下水道は都市内水では非常に重要です。

次に発展させるなら、

```text
2D Local-Inertial surface model
             ↕
       1D sewer network
```

という1D-2D couplingが面白いところです。

## まとめ

1m DEMを使った都市洪水シミュレーションでは、単に地形の最急降下方向を追うだけでは足りません。

重要なのは、

```text
地面の高さ
+
その瞬間の水深
=
水面の高さ
```

を使って、時間とともにセル間流量を更新することです。

今回の参考実装では、

- DEM1A
- Local-Inertial Approximation
- de Almeida型流量安定化
- semi-implicit Manning friction
- Adaptive CFL
- Wet/Dry処理
- Donor limiter
- 建物no-flow
- 道路粗度
- 屋根降雨再配分
- DEM境界補正

を組み合わせています。

1mまで格子を細かくすると、数値解法そのものと同じくらい、**建物・道路・DEM境界・質量保存・Wet/Dry処理**が重要になります。

## 参考文献

- P. D. Bates, M. S. Horritt, T. J. Fewtrell, **A simple inertial formulation of the shallow water equations for efficient two-dimensional flood inundation modelling**, Journal of Hydrology, 2010  
  [https://doi.org/10.1016/j.jhydrol.2010.03.027](https://doi.org/10.1016/j.jhydrol.2010.03.027)

- G. A. M. de Almeida, P. D. Bates, J. E. Freer, M. Souvignet, **Improving the stability of a simple formulation of the shallow water equations for 2-D flood modeling**, Water Resources Research, 2012  
  [https://doi.org/10.1029/2011WR011570](https://doi.org/10.1029/2011WR011570)

- G. A. M. de Almeida, P. D. Bates, **Applicability of the local inertial approximation of the shallow water equations to flood modeling**, Water Resources Research, 2013  
  [https://doi.org/10.1002/wrcr.20366](https://doi.org/10.1002/wrcr.20366)

- 国土地理院 基盤地図情報  
  [https://www.gsi.go.jp/kiban/](https://www.gsi.go.jp/kiban/)

- 国土地理院 基盤地図情報ダウンロードサービス  
  [https://service.gsi.go.jp/kiban/](https://service.gsi.go.jp/kiban/)

- 国土地理院 高精度標高データ  
  [https://www.gsi.go.jp/gazochosa/gazochosa41019.html](https://www.gsi.go.jp/gazochosa/gazochosa41019.html)

- 国土地理院 標高タイルの作成方法と地理院地図で表示される標高値について  
  [https://maps.gsi.go.jp/development/hyokochi.html](https://maps.gsi.go.jp/development/hyokochi.html)
