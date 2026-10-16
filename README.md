# Kaggriculture strategy analysis

Kaggle Featured Simulation Competition「Kaggriculture」のエージェント開発・
対戦評価・公開リプレイ分析をまとめたリポジトリ。

## Highlights

- v5からv12まで、土地利用・作物構成・12〜14頭の動的家畜選択を段階的に検証
- 2026-09-13時点のrank 1（Majkel1337、submission `56156662`）の公開10対戦を取得
- RAWリプレイとstep CSVの14,400行を照合し、不一致0件を確認
- 全10対戦でstep 0〜22の行動が完全一致し、最初の分岐がstep 23であることを確認
- 発行注文と成功注文を状態遷移から分離し、土地購入20/34件、hire 2,862/2,918件の成功を推定
- `DROP` overflowは全体でstrawberry 1個のみ。一方、日末のhand失効で259個を喪失
- rank 1の平均最終moneyは120,913.7。NEをday 6、SWをday 9に解放

詳細は以下を参照。

- [`docs/rank1_opening_consistency.md`](docs/rank1_opening_consistency.md): 23ステップ共通openingと最初の差分
- [`evaluation/results/exp093_rank1_replay_audit/report.md`](evaluation/results/exp093_rank1_replay_audit/report.md): 状態遷移audit
- [`experiments/rank1_reconstruction_plan.md`](experiments/rank1_reconstruction_plan.md): 再構築の設計と実験計画
- [`docs/reproduction.md`](docs/reproduction.md): 再現手順

## Directory layout

- `competition_files/`: Kaggle公式配布物（原本）
- `agents/`: エージェント実装
- `evaluation/`: ローカル対戦・集計コード
- `docs/`: rank 1分析と再現手順
- `experiments/`: 実験ごとの設定と出力
- `replays/`: ローカルおよびKaggle対戦リプレイ
- `submissions/`: 提出用成果物（`main.py` または `tar.gz`）
- `registries/experiments.csv`: 実験台帳
- `registries/submissions.csv`: 提出台帳
- `FINAL_SUBMISSION_CHECKLIST.md`: 最終提出候補の確認表
- `GAME_GUIDE_JA.md`: 競技仕様と戦略資源の日本語要約

公式仕様は [`competition_files/README.md`](competition_files/README.md) と
[`competition_files/AGENTS.md`](competition_files/AGENTS.md) を正とする。

Kaggle配布物、RAWリプレイ、大容量の生成結果、提出アーカイブはGit管理外。
このリポジトリには自作コード、実験台帳、レビュー済みの小さな集計結果のみを含める。
