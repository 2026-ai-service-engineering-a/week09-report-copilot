# CLAUDE.md

AI 서비스 엔지니어링 Track A 9주차 실습 랩. 박스오피스 리포트 코파일럿이고,
**화면과 에이전트가 같은 문서를 본다**는 것이 이 저장소의 주제다. 공통 역량
구간의 마지막 랩이라 5\~8주차의 층이 전부 여기 모인다. 이 문서는 이 저장소에서
작업하는 AI 도구를 위한 가이드다.

## 실행·검증 (전부 컨테이너에서)

```sh
docker compose up --build -d                        # api(8000) · web(3000) · db
docker compose exec api python -m scripts.load_data # 집계 테이블 적재
docker compose exec api pytest                      # 키·네트워크 없이 통과해야 한다
curl -s localhost:8000/health
```

로컬 파이썬으로 돌리지 않는다.

## Git 워크플로: git flow

- `develop`에서 `feature/*` 분기 → `develop` 머지. `main` 직접 커밋 금지
- **`main`이 곧 교재다.** 릴리즈는 `release/*`를 거쳐 `main` 머지 + annotated
  태그 + `develop` 역머지. 교안이 인용하는 코드·출력은 `main` 기준
- 커밋하면서 진행한다. 제목은 영어 명령형 한 줄

## 코드 규칙

- **코어는 문도 그래프도 모른다.** `core/`는 fastapi도 langgraph도 ag_ui도
  import하지 않는다. `graph/`는 `core`만, `api/`는 `core`와 `graph`만 본다.
  이 방향이 뒤집히면 이 저장소가 가르치려는 것이 사라진다
- **공유 상태의 스키마는 `core/schema.py` 하나다.** 에이전트가 고칠 수 있는
  것의 목록이 곧 이 파일이다. 여기 없는 필드는 어떤 경로로도 바뀌지 않는다
- **모델이 질의를 짠다.** 그래서 게이트가 둘이다. `core/harness.py`의
  `gate_query`가 첫 층, DB의 `reader` 계정 권한이 둘째 층. 어느 하나도 빼지 않는다
- 모델 문자열은 `core/config.py`에만 둔다
- **키가 없어도 돌아야 한다.** 각본 대역(`core/offline.py`)이 기본 경로이고
  테스트는 네트워크 없이 통과한다
- `data/`의 CSV는 저장소에 넣지 않는다. `scripts/fetch_boxoffice.py`가 받아 온다
