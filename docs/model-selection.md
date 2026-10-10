# Model Selection

보상 총점이 아니라 여러 지표로 고른다. 근거 데이터: `analytics/reports/exp003/`, `analytics/reports/final/`.

## 기준 (우선순위)

1. **포식자 사망률** (낮을수록) — 살아남지 못하면 사냥 수는 의미가 없다
2. **사냥 수** (처음 보는 seed + 처음 보는 맵 map_b 평균)
3. **무효 공격 비율** (낮을수록)
4. **reward hacking 탐지 플래그** 없음
5. 자원량 ±40%에서 성능 유지

학습 중 체크포인트 선택(`best_model.zip`)은 eval seed 10000–10004를 쓰므로 평가 세트와 겹친다.
그래서 보고·배포 모두 **선택 없이 마지막 체크포인트(`final_model.zip`)** 를 쓴다.

## 후보 비교 (각 20 seed, seen / map_b)

| 후보 | 사망률 | 사냥 | 무효 공격 | 탐지 플래그 | 자원 ×0.6 / ×1.4 사냥 |
|---|---|---|---|---|---|
| rule (기준선) | 0.00 / 0.00 | 2.10 / 2.25 | 0.56 / 0.44 | – | 1.95 / 2.05 |
| ppo_v1_s0 | 0.80 / 0.65 | 5.90 / 6.60 | 0.06 / 0.07 | dehydration_neglect | 6.35 / 5.60 |
| ppo_v2_s0 | 0.10 / 0.25 | 5.45 / 4.75 | 0.12 / 0.06 | water_farming (map_b 35%) | 4.90 / 4.60 |
| **ppo_v2_s1** | 0.20 / **0.05** | **7.05 / 7.15** | **0.02 / 0.02** | 없음 | 7.00 / 6.45 |
| ppo_v2_s2 | 0.15 / 0.10 | 6.55 / 6.35 | 0.03 / 0.04 | 없음 | 5.60 / 6.50 |

## 결정

**`ppo_v2_s1` → `models/ppo-v2.zip`** (sha256 `9406841a630f…`, 학습 메타데이터 `models/ppo-v2.metadata.json`).

- 두 평가 세트 평균 사망률 0.125로 v2_s2(0.125)와 같고, 사냥·무효 공격이 가장 좋다. 탐지 플래그 없음.
- ppo_v2_s0은 사망률은 낮지만 물가 머무름 의심과 사냥 감소로 제외.

## 한계

- 같은 평가 세트에서 3개 후보 중 하나를 고른 것이므로, 배포 모델의 수치는 약간 낙관적일 수 있다.
  실험 결론(v1 → v2 개선, PPO vs Rule)은 3개 학습 seed 전체 결과로 판단했다 ([experiments.md](experiments.md)).
- Rule은 여전히 사망률 0이다. "더 많이 사냥하지만 가끔 죽는" 정책과 "적게 사냥하지만 항상 사는" 정책 중 무엇이 좋은지는
  목적에 따라 다르다. 데모는 행동 차이가 잘 보이는 PPO v2를 쓴다.

## 재현

```sh
uv run python -m training.scripts.train_ppo --config ppo_v2 --seed 1
cp training/checkpoints/ppo_v2_s1/final_model.zip models/ppo-v2.zip
cp training/checkpoints/ppo_v2_s1/metadata.json models/ppo-v2.metadata.json
```
