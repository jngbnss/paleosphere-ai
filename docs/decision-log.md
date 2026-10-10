# Decision Log

| # | 날짜 | 결정 | 이유 | 대안 |
|---|---|---|---|---|
| D-001 | 2026-10-11 | 시각화는 2D 탑뷰 Godot | AI 증명에 3D 기여 없음, 일정 단축 | 3D Godot |
| D-002 | 2026-10-11 | Python sim이 single source of truth, Godot은 렌더+제어만 | 규칙 중복 구현 시 결정성 붕괴 | Godot이 sim, Python은 추론만 |
| D-003 | 2026-10-11 | 포식자 행동은 매크로 Discrete(7), 조향은 시뮬레이터 | 학습 난이도 감소, Rule과 동일 행동 공간으로 공정 비교 | 연속 이동 제어 |
| D-004 | 2026-10-11 | 거리 보상은 potential-based shaping만 | shadowing hacking 방지, 최적 정책 불변 | 단순 거리 감소 보상 |
| D-005 | 2026-10-11 | survival_reward는 v0에서 0 | REST 정체 정책 방지 | 소량 생존 보상 |
| D-006 | 2026-10-11 | 낮/밤만 구현, 날씨·번식·탐험자 모드·시계열 예측은 MVP 이후 | 4단계 범위 유지 | 전체 기능 |
| D-007 | 2026-10-11 | 루트 pyproject 하나 + uv, Python 3.12 | 이 PC에 uv 있음, 시스템 python 없음 | 패키지별 pyproject |
| D-008 | 2026-10-11 | map_b(물 이동, 식물 −40%)는 학습에 사용 안 함 | 보지 않은 자원 배치 일반화 평가 | 무작위 맵 학습 |
