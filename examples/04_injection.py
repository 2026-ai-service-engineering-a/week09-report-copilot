"""데이터 안에 지시가 섞여 있다면 — 심어 둔 시놉시스로 뚫어 본다.

    docker compose exec api python examples/04_injection.py

`scripts/load_data.py`가 `movie_cd=90000001`에 인젝션 한 줄을 심어 두었다.
**원본 데이터에는 없다.** 방어가 도는 것을 보이려고 우리가 놓은 함정이다.
"""

from core import db, harness

row = db.fetch_one("SELECT movie_nm, synopsis FROM movie WHERE movie_cd = '90000001'")
if not row:
    raise SystemExit("심어 둔 행이 없다. python -m scripts.load_data 를 먼저 돌린다")

name, synopsis = row
print(f"데이터에 이런 행이 있다: {name}\n")
print(synopsis)

print("\n① 탐지 — 가장 약한 층")
findings = harness.scan_injection(synopsis)
print(f"   {findings or '못 잡음'}")

print("\n② 경계 — 방어의 본체")
wrapped = harness.wrap_untrusted("movie.synopsis", synopsis)
print("   " + "\n   ".join(wrapped.splitlines()[:2]))
print("   …")
print("\n   시스템 프롬프트 쪽에는 이렇게 적혀 있다:")
for line in harness.BOUNDARY_RULES.strip().splitlines()[1:]:
    print(f"   {line}")

print("\n③ 검증 — 마지막 방어선")
print("""   결론에 "이 영화가 8월 1위입니다"가 섞여 들어와도, 검증자는 그 수치가
   집계 결과에 있는지만 본다. 대조는 코드가 하므로 설득당하지 않는다.
   세 층 중 유일하게 프롬프트로 뚫리지 않는 층이다.""")

print("\n④ 그리고 권한")
print("""   결론을 고치는 데 성공해도 상태 스키마 밖으로는 못 나간다.
   ui_language도 theme도 없으므로 화면 자체를 바꿀 방법은 없다.""")
