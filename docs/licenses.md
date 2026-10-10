# 사용 오픈소스 버전·라이선스

버전은 `uv.lock` 기준 (2026-10-11). 갱신: `uv pip list`.

| 구분 | 라이브러리 | 버전 | 라이선스 | 용도 |
|---|---|---|---|---|
| 시뮬레이션 | NumPy | 2.4.6 | BSD-3-Clause | 좌표·난수(SeedSequence). 2.5.x는 이 PC에서 DLL 차단 (D-009) |
| 시뮬레이션 | PyYAML | 6.0.3 | MIT | 월드·보상·학습 설정 |
| 시뮬레이션·서버 | Pydantic | 2.14.0 | MIT | 설정 검증, 서버 프로토콜 스키마 |
| 강화학습 | Gymnasium | 1.4.0 | MIT | `PaleoSpherePredator-v0` 환경, `check_env` |
| 강화학습 | Stable-Baselines3 | 2.9.0 | MIT | PPO |
| 강화학습 | PyTorch (CPU) | 2.14.1 | BSD-3-Clause | 정책 신경망, BC 사전학습 |
| 강화학습 | TensorBoard | 2.21.0 | Apache-2.0 | 학습 곡선·보상 component 로그 |
| 분석 | pandas | 3.0.6 | BSD-3-Clause | 평가 CSV·요약 |
| 분석 | Matplotlib | 3.11.2 | Matplotlib License (PSF 기반) | 보고서 그래프 |
| 서버 | FastAPI | 0.143.0 | MIT | `/ws/sim`, `/predict` |
| 서버 | Uvicorn | 0.54.0 | BSD-3-Clause | ASGI 서버 |
| 서버 | websockets | 17.2 | BSD-3-Clause | WebSocket 전송 |
| 테스트 | httpx | 0.28.1 | BSD-3-Clause | FastAPI TestClient |
| 개발 | pytest | 9.1.1 | MIT | 테스트 |
| 개발 | Ruff | 0.17.0 | MIT | 린트 |
| 시각화 | Godot Engine | 4.7.2-stable | MIT | 2D 관찰자 뷰어 (GDScript) |
| 도구 | uv | 0.12.10 | MIT / Apache-2.0 | 파이썬·의존성 관리 |

학습된 모델 체크포인트(`training/checkpoints/`, `models/`)는 저장소에 포함하지 않는다.
이 저장소 자체의 라이선스(LICENSE)는 아직 정하지 않았다 — 팀 결정 필요.
