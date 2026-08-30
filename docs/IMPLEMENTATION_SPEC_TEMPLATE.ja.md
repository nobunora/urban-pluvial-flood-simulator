# 詳細実装仕様書テンプレート（日本語訳）

> ステータス: Template / 日本語参考訳
>
> **正本（source of truth）は `IMPLEMENTATION_SPEC_TEMPLATE.md` の英語版です。**
> この日本語版は、人間が仕様作成ルールを読みやすくするための参考訳です。英語版と内容が衝突する場合は英語版を優先します。
>
> `PRODUCT_SPEC_DRAFT.md` を実装可能な詳細仕様へ変換するときに、このテンプレートを使います。
>
> 目標は、各実装単位を、無関係なモジュールや過去のチャット履歴を長期記憶していなくても理解できるようにすることです。

---

# 1. 記述ルール

1つの実装仕様書では、**1つのまとまりのある責務**だけを扱います。

悪い単位:

```text
データダウンロード、SFINCS実行、UI、結果描画を実装する。
```

良い単位:

```text
GSI標高取得
PLATEAU建物取得
Adaptive格子生成
SFINCSモデルwriter
SFINCS process runner
結果正規化
```

各実装単位は `PRODUCT_SPEC_DRAFT.md` の要件IDを参照しなければなりません。

---

# 2. 必須ヘッダ

すべての実装単位で以下のヘッダを使用します。

```markdown
# <Module name>

## Related product requirements

- DATA-001
- DATA-003

## Purpose

このモジュールが存在する理由を1段落で記述する。

## In scope

- ...

## Not implemented in this module

- ...

## Future extension points

- ...

## Permanent non-goals

- ...
```

`Not implemented` セクションは、項目が1つしかない場合でも必須です。

---

# 3. 入力と出力

処理説明より先に、必ず入力を定義します。

```markdown
## Inputs

### Input A

Type:
Required/optional:
Units:
Coordinate system:
Validation:
Source:

## Outputs

### Output A

Type:
Units:
Coordinate system:
Persistence:
Consumer:
```

明示的な参照なしに「前と同じ」「既存オブジェクト」「通常の形式」などの表現を使ってはいけません。

---

# 4. 正常系処理

正常系は短い番号付き手順で書きます。

```markdown
## Normal flow

1. bounding boxを検証する。
2. 必要なsource tileを決定する。
3. cacheを確認する。
4. 不足tileをdownloadする。
5. responseを検証する。
6. elevationをdecodeする。
7. mosaicする。
8. reprojectする。
9. processed outputとmanifest metadataを書き込む。
```

可能な限り、1ステップにつき1つの処理だけを記述します。

---

# 5. 状態と永続化

モジュールが状態を保持する場合は明示的に定義します。

```markdown
## State

### Cache state

- key:
- value:
- invalidation condition:
- versioning rule:

### Project state

- field:
- default:
- serialization:
```

状態を保持しない場合は、statelessであることを明記します。

---

# 6. エラーとfallback

外部データまたはエンジンを扱うすべてのモジュールには、エラー表を含めます。

```markdown
## Error handling

| Condition | Detection | User-facing result | Internal action | Retry |
|---|---|---|---|---|
| timeout | ... | ... | ... | yes |
| 404/no coverage | ... | ... | ... | no |
| malformed data | ... | ... | ... | no |
```

物理精度やデータ出典へ影響するfallbackを黙って行ってはいけません。

---

# 7. 数値・物理仮定

水理的な意味を変えるモジュールは、ソフトウェア挙動とは別に物理仮定を記述します。

例:

```markdown
## Physical assumptions

- rainfall is spatially uniform;
- infiltration is not modelled;
- roof rainfall is redistributed with mass conservation;
- building interior storage is not modelled.
```

物理仮定を実装メモの中に埋め込んではいけません。

---

# 8. 外部依存

すべての外部依存について以下を記録します。

```markdown
## External dependencies

### Dependency name

Purpose:
Official documentation:
Version policy:
License/terms note:
Network required:
Fallback:
```

不安定・試験提供のAPIでは、互換性境界を明示的に定義します。

---

# 9. テスト

各実装単位は、実装開始前にテストを定義します。

```markdown
## Unit tests

### TEST-<module>-001

Given:
When:
Then:

## Integration tests

### TEST-<module>-INT-001

Environment:
Given:
When:
Then:
Expected artifacts:

## Failure tests

### TEST-<module>-ERR-001

Given:
When:
Then:
```

数値モジュールでは「近い」などの曖昧な表現ではなく、許容差を定義します。

---

# 10. 受入条件

受入条件は観測可能でなければなりません。

悪い例:

```text
正しく動作する。
```

良い例:

```text
fixture datasetに対して、decode済み標高値が期待配列と0.01 m以内で一致し、row 0が文書化された地理方向へ対応する。
```

閾値がまだ未決定の場合は明示します。

```text
TBD-PRODUCT-DECISION
```

文書を埋めるためだけに閾値を捏造してはいけません。

---

# 11. ログと診断

データ、格子、エンジン、降雨モジュールでは診断出力を定義します。

最低限有用な診断情報:

- 使用プロバイダ
- 利用可能な場合のdataset/version ID
- 入力bounds
- grid/cell数
- fallback使用有無
- mass-balance check
- engine version
- 各stageの経過時間（診断用）
- 開発者向け障害詳細

ユーザー向けログと開発者向けログは異なる詳細度で構いません。

---

# 12. セキュリティ、プライバシー、ライセンス

ネットワーク・データモジュールは最低限以下へ回答します。

- ユーザーが選択した座標を外部プロバイダへ送信するか？
- 住所を保存するか？
- cache fileを共有してよいか？
- attributionが必要か？
- binary/dataを再配布できるか？
- authenticationが存在するか？
- rate limit / service restrictionが文書化されているか？

認証またはライセンス同意制限を自動的に回避してはいけません。

---

# 13. モジュール完了チェック

各モジュール仕様書の末尾に以下のchecklistを置きます。

```markdown
## Module check

- [ ] Product requirement IDs are listed.
- [ ] In-scope behavior is explicit.
- [ ] Not-implemented behavior is explicit.
- [ ] Future extension points are explicit.
- [ ] Permanent non-goals are explicit where applicable.
- [ ] Inputs and outputs are fully defined.
- [ ] Units and coordinate systems are defined.
- [ ] Normal path is defined.
- [ ] Error/fallback paths are defined.
- [ ] External dependencies and terms are identified.
- [ ] Physical assumptions are visible.
- [ ] Unit/integration/failure tests are specified.
- [ ] Acceptance criteria are observable.
- [ ] The module can be implemented without relying on unrelated chat history.
```

日本語で確認すると以下の意味です。

- [ ] 製品要件IDが列挙されている。
- [ ] 対象範囲が明示されている。
- [ ] 実装しない内容が明示されている。
- [ ] 将来拡張点が明示されている。
- [ ] 必要に応じて恒久的非目標が明示されている。
- [ ] 入出力が完全に定義されている。
- [ ] 単位・座標系が定義されている。
- [ ] 正常系が定義されている。
- [ ] エラー・fallback系が定義されている。
- [ ] 外部依存・利用条件が特定されている。
- [ ] 物理仮定が見える形で記述されている。
- [ ] Unit / integration / failure testが定義されている。
- [ ] 受入条件が観測可能である。
- [ ] 無関係なチャット履歴に依存せず実装できる。

---

# 14. 推奨する仕様作成順序

下流モジュールが安定した上流データ契約を参照できるよう、詳細実装仕様書は以下の順番で作成します。

1. Project state and common geometry types
2. Map/geocoding and analysis-area model
3. GSI elevation provider
4. PLATEAU provider
5. OSM fallback provider
6. Terrain normalization/cache
7. Rainfall scenario model
8. Roof rainfall allocation
9. Adaptive grid classifier
10. SFINCS model/subgrid writer
11. SFINCS engine bootstrap
12. SFINCS runner
13. Result normalization
14. Visualization
15. Manifest/project persistence
16. End-to-end validation harness

上流ドメインモジュールが所有すべきデータ構造を、UI実装仕様側で先に勝手に作ってはいけません。
