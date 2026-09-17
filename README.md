# week09-report-copilot

AI 서비스 엔지니어링 Track A **9주차 실습 랩**. 박스오피스 리포트를 사람과
에이전트가 **같이 고치는** 화면이다.

공통 역량 구간의 마지막 랩이고, 10주차부터 각자의 프로젝트에서 베껴 쓸
레퍼런스 구현이다. 5\~8주차에 배운 층이 전부 여기 모인다.

- 교안: [9주차 · 화면 안의 에이전트, 그리고 스택의 완성](https://2026-ai-service-engineering-a.github.io/ai_service_engineering-track_a/course/session-09/)

## 이 랩이 보여주는 것

화면에 AI를 덧붙이는 흔한 구조는 지시대명사 하나에 무너진다. 사용자가 화면에서
섹션을 고른 채 "이거 빼줘"라고 하면 챗봇은 무엇을 빼야 할지 모른다. 화면이 가진
상태와 에이전트가 가진 맥락이 **두 벌**이기 때문이다.

이 저장소에는 화면 모드가 넷 있고, 코어는 하나다.

| 모드 | 관계 | 들어가는 것 |
| --- | --- | --- |
| `v0` | AI가 화면 **뒤에** | 폼형. 3주차 헤드리스 구조 그대로 |
| `v1` | AI가 화면 **옆에** | 챗 위젯. **여기서 무너진다** |
| `v2` | AI가 화면 **안에** | AG-UI 공유 상태. `STATE_DELTA` |
| `v3` | AI가 화면을 **만든다** | 생성 UI와 승인 카드 |

같은 한마디를 모드를 바꿔 가며 쳐 보는 것이 이 랩의 첫 실습이다. 섹션을
고른 채 "이거 빼줘"라고 하면 v1은 되묻고 v2는 지운다. **모델도 그래프도
같은 것을 쓴다.** 갈린 것은 요청이 선택을 실어 오느냐 하나뿐이다.

화면 왼쪽 위에서 모드를 바꾸면 같은 코어에 다른 껍데기가 붙는다.

## 무엇을 말할 수 있나

**기간**은 코드가 읽는다. 모델에게 묻지 않으므로 날짜가 틀리지 않고, 데이터가
없는 구간은 잘라서 그 사실을 알려 준다.

```plaintext
2026년 1월부터          2026년 3월          1월부터 6월까지
3분기                  최근 3개월           2026-01-01부터 2026-06-30까지
```

**축**은 아홉 가지다. 말하지 않으면 기간을 보고 정한다. 1년치를 일자별로
그리면 점이 365개라 아무것도 안 보이기 때문이다.

```plaintext
시간   월별 · 주별 · 요일별
범주   국적별 · 장르별 · 배급사별 · 등급별 · 구분별 · 영화별
```

**지표**는 `data/metrics.yaml`에 있다. 모르는 용어를 말하면 지어내지 않고
목록을 돌려준다. 계산할 수 없는 지표(좌석판매율 같은 것)는 그렇다고 답한다.

한번 이어서 쳐 보면 공유 상태가 무엇인지 바로 보인다.

```plaintext
2026년 1월부터 월별 관객수 보여줘     기간이 바뀌고 섹션이 다시 채워진다
국적별로도 보여줘                   섹션이 하나 는다
3분기만                           기간만 바뀌고 있던 섹션이 전부 다시 돈다
(섹션을 클릭하고) 이거 빼줘          지운다. 모델 호출 0회
막대로 바꿔줘                      차트 종류만 바뀐다. 모델 호출 0회
이 리포트 발행해줘                  승인 카드가 뜬다
```

## 빠른 시작

```sh
git clone https://github.com/2026-ai-service-engineering-a/week09-report-copilot.git
cd week09-report-copilot
cp .env.sample .env
docker compose up --build -d
docker compose exec api python -m scripts.load_data
```

- 화면: <http://localhost:3000>
- 계약: <http://localhost:8000/docs>
- 테스트: `docker compose exec api pytest`

**키가 하나도 없어도 전부 돕니다.** 키가 없으면 `core/offline.py`의 각본 대역이
모델을 대신합니다. 가짜인 것은 모델뿐이고 질의도, 상태 패치도, 예산도 진짜로
일어납니다.

## 데이터

영화진흥위원회 영화관입장권통합전산망(KOBIS)의 일별 박스오피스다. **API 키가
필요 없다.** 공개 통계 화면에서 주 단위로 받아 온다.

```sh
docker compose exec api python -m scripts.fetch_boxoffice   # 1년치 수집 (약 2분)
docker compose exec api python -m scripts.load_data         # 정제·적재
```

원본 CSV는 저장소에 넣지 않는다. `data/`는 비어 있고 스크립트가 채운다.
수집·정제에서 무엇을 발견했는지는 강의 저장소의
`docs/week09-boxoffice-data.md`에 전수조사 기록으로 남아 있다.

기본 기간은 2025-09-01부터 2026-08-31까지다. 바꾸면 교안의 수치와 달라진다.

## 구조

```plaintext
core/     코어. 문도 그래프도 모른다
  schema.py     ★ 공유 상태. 에이전트가 고칠 수 있는 것의 전부
  tools.py      run_query · lookup_metric
  harness.py    질의 게이트 · 예산 · 데이터 경계
  metrics.py    지표 정의 검색 (4주차 계보)
  llm.py        모델로 나가는 단 한 자리
graph/    7주차 자산. 요청마다 다른 경로가 돈다
  router.py     한 스텝인가 ReAct인가 계획인가
  build.py      계획 → 섹션(병렬) → 검증 → 서술
api/      문
  agui.py       ★ AG-UI 엔드포인트
  main.py       v0 폼형 · v1 챗 위젯 · /config
web/      화면. v0~v3 네 모드
scripts/  수집·적재
examples/ 교안이 인용하는 실행 예제
```

## 예제

교안의 장면들을 하나씩 돌려 본다.

```sh
docker compose exec api python examples/01_chat_widget_breaks.py  # v1이 무너지는 장면
docker compose exec api python examples/02_state_delta.py         # 채팅 한 줄 → JSON Patch
docker compose exec api python examples/03_loop_routes.py         # 요청별 루프와 호출 수
docker compose exec api python examples/04_injection.py           # 시놉시스에 섞인 지시
```

## 라이선스

강의 자료의 라이선스는 추후 명시 예정입니다. 박스오피스 데이터의 출처와
이용 조건은 영화진흥위원회 영화관입장권통합전산망을 따릅니다.
