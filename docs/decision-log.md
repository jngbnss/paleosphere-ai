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
| D-009 | 2026-10-11 | numpy `<2.5` 고정 | 이 PC에서 numpy 2.5.x의 `_common` DLL이 Windows 애플리케이션 제어(Smart App Control)에 차단됨. 2.4.6은 정상 | 정책 해제 |
| D-010 | 2026-10-11 | shaping potential을 Φ = coef·(1 − d/vision) ≥ 0으로 정의 | Φ ≤ 0이면 γ<1에서 제자리 대기가 (1−γ)|Φ| 만큼 양의 보상을 받음 (테스트로 발견) | Φ = −coef·d/vision |
| D-011 | 2026-10-11 | 학습 시 `torch.set_num_threads(1)`, 이동·충돌은 float 연산 | 12 스레드에서 PPO 150 steps/s → 1 스레드 1,150. numpy 2원소 배열 오버헤드 제거로 env 단일 650 → 2,570 steps/s. 결과 해시는 동일 | 기본 스레드, numpy 벡터 연산 |
| D-012 | 2026-10-11 | 보상 v1: shaping γ=1, 명중·배고픔·목표 없는 GIVE_UP 항목 추가 | Exp 001 분석 (reward-design.md) | 보상 v0 유지 |
| D-013 | 2026-10-11 | PPO 학습에 규칙 기반 시연 BC 사전학습 + 근접 시작 커리큘럼(30%) 사용 | 보상 수정만으로는 학습 중 명중 0회 (탐색 실패). 평가는 기본 배치·평가 seed만 | 학습 step 증가, 에피소드 단축 |
