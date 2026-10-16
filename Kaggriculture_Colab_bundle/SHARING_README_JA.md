# Kaggriculture 共有パッケージ

このパッケージは、Kaggle Featured Simulation Competition
「Kaggriculture」で作成したルールベースエージェント、ローカル評価基盤、
実験記録、提出記録を共有するためのものです。

## 収録内容

- `agents/`: v0から現在版までのエージェント
- `agents/v6_full_utilization/main.py`: 現在のv12（動的12〜14頭＋相手・市場対応）
- `evaluation/evaluate.py`: 複数seed・両プレイヤー位置で評価するスクリプト
- `experiments/`, `results/`, `evaluation/results/`: 各実験の軽量な`summary.json`と`results.csv`
- `registries/experiments.csv`: 実験台帳
- `registries/submissions.csv`: Kaggle提出台帳
- `competition_files/README.md`: 公式ゲーム仕様
- `competition_files/AGENTS.md`: 公式エージェント作成ガイド
- `GAME_GUIDE_JA.md`: 日本語のゲーム解説
- `FINAL_SUBMISSION_CHECKLIST.md`: 最終提出チェックリスト

容量の大きいreplay JSON、ログ、Pythonキャッシュ、認証情報は含めていません。

## エージェントの変遷

| ディレクトリ | 概要 |
|---|---|
| `v0_goose_carrot` | ガチョウと小麦・にんじんの初期ベースライン |
| `v1_investment_livestock` | 序盤の家畜投資を強化 |
| `v2_livestock_scale3` | 家畜投資規模と飼料管理を拡大 |
| `v3_close5_wheat_strawberry` | 倉庫近傍5頭、小麦からいちごへの展開 |
| `v4_market_land_ne` | 市場価格と土地購入ゲートを導入 |
| `v5_near_first_fill` | 倉庫から近い順に土地を埋める方式 |
| `v6_full_utilization` | その後のv6〜v12。動的人員、区画担当、市場・相手対応、動的家畜数を統合 |

`v6_full_utilization`というディレクトリ名は開発開始時の名称です。中の
`main.py`は継続的に改善され、共有時点ではv12です。過去にKaggleへ提出した
各時点のハッシュは`registries/submissions.csv`に記録されています。

## 必要環境

- Python 3.11以降を推奨
- `kaggle-environments`
- Kaggleへ提出する場合のみ`kaggle` CLI

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U kaggle-environments kaggle
```

## ローカル評価

リポジトリのルートで次を実行します。

```bash
python evaluation/evaluate.py \
  --agent agents/v6_full_utilization/main.py \
  --opponents starter random pass \
  --seeds 0 1 2 3 4 \
  --output local_results/v12_baselines
```

`--save-replay`を付けると各試合のreplay JSONも保存されます。評価結果には
勝敗、最終資金、資金差、失敗率、行動内訳、実行時間が含まれます。

## Kaggle提出

`v12_submission.tar.gz`は、ルート直下に`main.py`がある提出用ファイルです。
競技参加とルール同意を本人が済ませた後、次の形式で提出できます。

```bash
env -u KAGGLE_API_TOKEN kaggle competitions submit kaggriculture \
  -f v12_submission.tar.gz \
  -m "v12 dynamic 12-14 livestock"
```

Kaggle評価中は外部通信できませんが、現在のエージェントは単一Pythonファイルで
外部依存やネットワークアクセスを必要としません。

## 注意事項

- 競技ルールと利用条件は共有・提出前に各自で確認してください。
- Leaderboard ratingは対戦のたびに変動します。
- ローカル勝率だけで最終候補を決めず、実戦replayと対戦相手の分布も確認してください。
- 最新2提出のみが最終評価対象になるため、提出順を管理してください。
