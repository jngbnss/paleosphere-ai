# TODO

완료 기록은 [PLAN.md](PLAN.md), 결과는 [docs/experiments.md](docs/experiments.md).
이 파일은 **지금까지 상태 요약 + 앞으로 할 일**이다. 항목을 시작하면 PLAN.md에 Phase로 옮긴다.

## 지금까지 (2026-10-11 기준, Phase 0–9 ✅)

| Phase | 내용 | 핵심 결과 |
|---|---|---|
| 0–1 | 결정론적 생태계 sim + 규칙 기반 포식자 기준선 | 골든 해시 테스트 |
| 2–3 | Gymnasium 환경, PPO(BC 사전학습), reward hacking·일반화 평가 | Exp 001–003, 보상 v2 |
| 4 | FastAPI WebSocket 서버 + Godot 2D 관찰자 뷰어 | 포트 8790 |
| 5 | ONNX 내보내기, GDScript MLP, `client` 모드 | SB3·ONNX·GDScript 행동 100% 일치 |
| 6 | 번식·노화(`ecosystem` 맵) + 개체수 예측 | Exp 004: GBM MAE 6.13→3.07 (500 tick) |
| 7 | PettingZoo 초식 무리 학습(`herd-v1`) | Exp 005: 처음 보는 PPO 포식자 상대 생존 1.55–2.50 vs 규칙 0.85–0.95 |
| 8 | 탐험자 모드 (스캔·목격·현장 보고서) | sim 비간섭 (해시 동일) |
| 9 | 3D 1인칭 탐험 뷰어 (`scenes/explore3d.tscn`, `dev.ps1` 기본) | headless·창 스모크 통과, D-019 |

실행: `powershell -ExecutionPolicy Bypass -File scripts\dev.ps1` (3D) · `-View2D` (2D) · `-Smoke` (창 없이 검사)

## 확인 필요 (사람이 직접)

- [ ] 3D 뷰어 손 조작감: 마우스 감도(`MOUSE_SENS 0.0025`), 걷기 4.5 m/s · 달리기 10 m/s, 기본 속도 1배(5 tick/s)가 적당한지
- [ ] 3D 창이 첫 실행 후 닫힘 — 사용자가 닫은 건지 크래시인지 불명 (종료 코드 0, 로그 없음). 재현되면 원인 조사
- [ ] 2D 뷰어 연결 즉시 자동 시작이 실제 창에서 동작하는지 (스모크는 통과, 육안 확인 안 함)

## 3D 뷰어 개선

- [ ] `dev.ps1`에 Godot 로그 파일 남기기 (`--log-file`), 크래시 원인 추적용
- [ ] 공룡 모델 품질: CC0 glTF 공룡 모델(애니메이션 포함) 교체 옵션 — 라이선스 `docs/licenses.md` 기록, 절차 생성 모델은 대체용으로 유지
- [ ] 지형 높낮이(완만한 언덕), 물가 경사, 풀 흔들림 셰이더
- [ ] 소리: 발소리·울음·사냥 (CC0 효과음)
- [ ] 개체가 50마리 이상일 때 성능 측정 (draw call, FPS), 필요하면 LOD·MultiMesh
- [ ] 3D 화면 설정: 맵·포식자/초식 정책·seed 고르는 시작 메뉴 (지금은 ecosystem·ppo·herd-v1 고정)
- [ ] 리플레이 파일 3D 재생
- [ ] 따라가기 카메라 충돌(바위 관통) 처리

## AI·시뮬레이션

- [ ] 번식하는 `ecosystem` 맵에서 포식자 PPO 재학습 (지금 ppo-v2는 map_a 단일 포식자 학습)
- [ ] 초식·포식 동시 학습(self-play / 교대 학습), 군비 경쟁 곡선 기록 → Experiment 006
- [ ] herd-v1 seed 간 편차 분석 (s2만 배포), 더 많은 seed 평가
- [ ] 개체수 예측: 장기(5,000 tick+) 지평, 멸종 확률 분류 모델
- [ ] 개체 간 충돌을 sim에 넣을지 결정 — 넣으면 골든 해시·모델 재생성 필요 (지금은 3D 화면에서만 벌림, D-019)

## 인프라

- [ ] CI Godot 잡은 import·파싱 검사만 함 → 서버 띄워서 2D·3D `--smoke`까지 실행
- [ ] 학습 모델(`models/*.zip`)이 Git에 없음 — 릴리스 자산 또는 다운로드 스크립트로 배포
- [ ] numpy `<2.5`, scikit-learn `<1.8` 고정 (이 PC Smart App Control DLL 차단, D-009) — 정책 바뀌면 해제
